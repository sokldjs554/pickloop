"""Class-balanced linear readout, reference similarities and open-set decisions."""
import numpy as np
from scipy.linalg import solve


def unit(vectors):
    x = np.asarray(vectors, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-9)


def allowed(row, support, score, margin):
    return row['support'] >= support and row['score'] >= score and row['margin'] >= margin


def calibrate(known, truth, outside):
    """Choose floors on development data while retaining 95% of named correct decisions."""
    correct = np.array([r['top1'] == t for r, t in zip(known, truth, strict=True)])
    if not correct.any() or not outside:
        raise ValueError('need correct known and independent negative calibration examples')
    names = ['support', 'score', 'margin']
    pos = np.array([[r[k] for k in names] for r in known])
    neg = np.array([[r[k] for k in names] for r in outside])
    # At most floor(5%) correct observations may be lost. Try empirical order
    # statistics including the exact boundary point used by the >= rule.
    max_lost = int(correct.sum()) // 20
    indices = np.unique(np.linspace(0, max_lost, min(9, max_lost + 1), dtype=int))
    # Scores at a floor are accepted. Search the first representable value above
    # observed negative scores, with numerical slack for single/batched BLAS.
    outside_indices = np.unique(np.linspace(len(neg) // 2, len(neg) - 1, min(17, len(neg)), dtype=int))
    candidates = []
    for j in range(len(names)):
        negative_edges = np.sort(neg[:, j])[outside_indices] + 1e-5
        candidates.append(np.unique(np.r_[-2., np.sort(pos[correct, j])[indices], negative_edges]))
    best, result = None, None
    for support in candidates[0]:
        for score in candidates[1]:
            for margin in candidates[2]:
                floors = np.array([support, score, margin])
                kept = np.all(pos >= floors, axis=1)
                retained = int(np.sum(kept & correct))
                if retained < correct.sum() - max_lost:
                    continue
                accepted = int(np.all(neg >= floors, axis=1).sum())
                wrong = int(np.sum(kept & ~correct))
                key = (accepted, -retained, wrong, support + score + margin)
                if best is None or key < best:
                    best = key
                    result = dict(support=float(support), score=float(score), margin=float(margin),
                                  known_correct_before=int(correct.sum()), known_correct_after=retained,
                                  known_wrong_after=wrong, outside_accepted=accepted)
    return result


class CatalogueHead:
    def __init__(self, names, gallery, labels, slopes, intercept):
        self.names = list(names)
        self.gallery_storage = np.asarray(gallery, dtype=np.float16)
        self.gallery = unit(self.gallery_storage)
        self.labels = np.asarray(labels, dtype=int)
        self.slopes = np.asarray(slopes, dtype=np.float32)
        self.intercept = np.asarray(intercept, dtype=np.float32)
        c = len(self.names)
        if (c < 2 or len(set(self.names)) != c or 'UNKNOWN' in self.names
                or self.gallery.ndim != 2 or len(self.labels) != len(self.gallery)
                or set(self.labels) != set(range(c)) or self.slopes.shape != (self.gallery.shape[1], c)
                or self.intercept.shape != (c,) or not np.isfinite(self.gallery).all()
                or not np.isfinite(self.slopes).all() or not np.isfinite(self.intercept).all()):
            raise ValueError('invalid catalogue head or missing reference class')
        self.neighbour_weight = 0.
        self.min_support = self.min_score = self.min_margin = -2.

    @classmethod
    def fit(cls, names, vectors, labels, ridge):
        x = unit(vectors)
        y = np.asarray(labels, dtype=int)
        c = len(names)
        if set(y) != set(range(c)) or len(x) != len(y) or ridge <= 0:
            raise ValueError('train requires every catalogue class and positive regularization')
        weight = len(x) / (c * np.bincount(y)[y])
        center = np.average(x, weights=weight, axis=0)
        targets = np.eye(c)[y]
        center_y = np.average(targets, weights=weight, axis=0)
        z = x - center
        gram = z.T @ (z * weight[:, None])
        gram.flat[::len(gram) + 1] += ridge
        w = solve(gram, z.T @ ((targets - center_y) * weight[:, None]), assume_a='pos')
        return cls(names, x.astype(np.float16), y, w, center_y - center @ w)

    def evidence(self, vectors):
        x = unit(vectors)
        similarities = x @ self.gallery.T
        support = np.empty((len(x), len(self.names)), dtype=np.float32)
        for i in range(len(self.names)):
            scores = similarities[:, self.labels == i]
            k = min(3, scores.shape[1])
            support[:, i] = np.partition(scores, -k, axis=1)[:, -k:].mean(axis=1)
        return x @ self.slopes + self.intercept, support

    def decisions(self, linear, support):
        combined = linear + self.neighbour_weight * support
        best = np.argmax(combined, axis=1)
        runners = np.partition(combined, -2, axis=1)[:, -2]
        rows = []
        for i, win in enumerate(best):
            name = self.names[win]
            row = dict(top1=name, support=float(support[i, win]), score=float(linear[i, win]),
                       margin=float(combined[i, win] - runners[i]))
            row['prediction'] = name if allowed(row, self.min_support, self.min_score, self.min_margin) else 'UNKNOWN'
            rows.append(row)
        return rows

    def predict(self, vectors):
        return self.decisions(*self.evidence(vectors))

    def save(self, path):
        from .catalogue_features import FEATURE_VERSION
        np.savez_compressed(path, schema=1, encoder=FEATURE_VERSION, names=self.names, gallery=self.gallery_storage,
                            labels=self.labels.astype(np.int16), slopes=self.slopes, intercept=self.intercept,
                            neighbour_weight=self.neighbour_weight, floors=[self.min_support,self.min_score,self.min_margin])

    @classmethod
    def load(cls, path):
        from .catalogue_features import FEATURE_VERSION
        with np.load(path, allow_pickle=False) as data:
            if data['schema'].item() != 1 or data['encoder'].item() != FEATURE_VERSION:
                raise ValueError('incompatible catalogue archive')
            head = cls(data['names'].tolist(), data['gallery'], data['labels'], data['slopes'], data['intercept'])
            head.neighbour_weight = float(data['neighbour_weight'].item())
            head.min_support, head.min_score, head.min_margin = data['floors'].tolist()
            return head
