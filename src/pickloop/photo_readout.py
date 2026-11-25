"""Keep printed flavour, sized catalogue name and optical order identity distinct."""
import subprocess

from .juice_gate import TARGETS
from .pack_barcode import REGISTERED_GTINS, read_ean13
from .package_size import printed_size, read_size_band
from .product_text import APPLE_WORD, GRAPE_WORD, ORANGE_WORD, OTHER, normalized, printed_flavour, recognize_exact
from .registered_pack import match_pack


def photo_readout(result, require_gtin=False, rgb=None):
    panel = None
    if rgb is not None and not result["recognition_gtins"]:
        panel = match_pack(rgb)
        if panel and panel["status"] == "matched" and result["recognition_source"] == "baseline":
            # A previously accepted generic class bypassed the package-barcode check.
            # Apply the same unregistered/multiple/code-text veto before rescuing its photo.
            result = recognize_exact(dict(result, prediction="UNKNOWN"), lambda: rgb)
            if result["recognition_gtins"]:
                panel = None
    candidate = result["prediction"]
    identity = result
    if require_gtin and rgb is not None and result["recognition_source"] == "baseline" and read_ean13(rgb):
        identity = recognize_exact(dict(result, prediction="UNKNOWN"), lambda: rgb)
    codes = identity["recognition_gtins"]
    confirmed = None
    if identity["recognition_source"] == "barcode" and identity["recognition_reason"] == "registered_gtin" and len(codes) == 1:
        sku = REGISTERED_GTINS.get(codes[0])
        if sku == identity["prediction"]:
            confirmed = sku

    reads = [normalized(line) for line in identity["recognition_text"]]
    words = [name for name, pattern in (("apple", APPLE_WORD), ("orange", ORANGE_WORD), ("grapefruit", GRAPE_WORD))
             if sum(bool(pattern.search(line)) for line in reads) >= 2]
    flavour = candidate if candidate in TARGETS else None
    if flavour is None and result["recognition_source"] in ("package_text", "registered_panel_and_text"):
        flavour, _ = printed_flavour(reads, result["recognition_source"] == "registered_panel_and_text", veto_size=False)

    name = None if candidate == "UNKNOWN" else candidate
    name_reason = result["recognition_reason"]
    order_reason = identity["recognition_reason"]
    proposed = panel["product"] if panel and panel["status"] == "matched" else None
    size_reads = []
    size_status, evidence = "not_applicable", []
    if flavour or confirmed or reads or codes or proposed:
        if rgb is not None and (flavour or confirmed or proposed):
            try:
                size_reads = read_size_band(rgb)
            except (OSError, subprocess.SubprocessError):
                # The original print reads and the optical barcode remain independently usable.
                pass
        size_status, evidence = printed_size([*reads, *size_reads])
        if confirmed:
            if size_status == "contradictory":
                confirmed, order_reason = None, "barcode_text_conflict"
            else:
                size_status = "registered_gtin"

    # A repeated printed net quantity can resolve two sizes of the same flavour.
    # Foreign 1 L packs and packs of uncertain size still compete on artwork.
    if panel and "if_printed_one_litre" in panel:
        panel = panel.copy()
        conditional = panel.pop("if_printed_one_litre")
        if size_status == "printed_1l" and conditional["product"] == flavour and not codes:
            panel = {**conditional, "resolved_by": "corroborated_printed_volume"}

    artwork_name = None
    if panel and panel["status"] == "matched":
        proposed = panel["product"]
        foreign_words = {"God-Morgon-Apple-Juice": ("orange","grapefruit"),
                         "God-Morgon-Orange-Juice": ("apple","grapefruit"),
                         "God-Morgon-Orange-Red-Grapefruit-Juice": ("apple",)}[proposed]
        if (not codes and (not flavour or flavour == proposed)
                and not any(word in words for word in foreign_words)
                and result["recognition_reason"] != "conflicting_flavours"
                and not any(OTHER.search(line) for line in reads)):
            artwork_name = proposed
    if candidate in TARGETS or flavour:
        name = None
        if size_status == "contradictory":
            name_reason = "size_contradiction"
        elif confirmed == flavour and confirmed:
            name, name_reason = confirmed, "registered_gtin"
        elif not codes and size_status == "printed_1l" and candidate in TARGETS:
            name, name_reason = candidate, "flavour_and_printed_1l"
        elif not codes and candidate in TARGETS:
            name_reason = "size_unverified"
    if panel and not codes:
        if artwork_name and size_status != "contradictory":
            name = flavour = artwork_name
            name_reason = "registered_pack_artwork"
            if size_status != "printed_1l":
                size_status = "registered_artwork"
            result = dict(result, recognition_source="registered_artwork", recognition_reason=name_reason)
        elif name in TARGETS or candidate in TARGETS or panel["status"] == "matched":
            name = None
            if size_status != "contradictory":
                name_reason = "competing_pack_artwork" if panel["status"] == "ambiguous" else "incompatible_pack_artwork"
            else:
                name_reason = "size_contradiction"
    return dict(result, registered_pack=panel, photo_name=name, photo_name_reason=name_reason, flavour_candidate=flavour,
                size_status=size_status, size_evidence=evidence, size_readings=size_reads, printed_fruit_words=words,
                confirmed_order_sku=confirmed, confirmed_gtin=codes[0] if confirmed else None,
                order_check_reason=order_reason, order_check_gtins=codes,
                prediction=(confirmed if require_gtin else name) or "UNKNOWN")
