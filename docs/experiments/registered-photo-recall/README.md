# Registered carton artwork

The gallery contains 31 enrollment photographs. **Every source in [enrollment.json](enrollment.json) is fit data**, including its crops, resizes and transcodes. Seven originals come from the official Grocery Store Dataset training split. The remaining 24 are previously labelled photographs of registered or incompatible cartons. The source polygons exclude the shelf, hand and other products wherever possible. There are 20 front panels, six ingredient panels and five nutrition panels.

The three registered identities are Swedish God Morgon apple 1 L (7310865074225), orange 1 L (7310860007372) and orange/red grapefruit 1 L (7310860007259). The gallery also contains other flavours, Finnish market cartons, 250 mL packs and Swedish 1.75 L packs. The colour of the fruit and the God Morgon wordmark recur across these products.

The matcher locates ORB keypoints and fits a planar transformation with RANSAC. The transformation must preserve orientation and place enough of the panel within the picture. On a front, the matcher uses the transformation to compare the colour and brightness pattern on the lower part of the carton, where there are few keypoints. On a nutrition panel it requires aligned details in the heading, numeric column and lower text. A close match to incompatible artwork can withhold a name even when the image shows a 1 L quantity.

A visual match supplies a photo name. Optical barcode decoding supplies order confirmation. The readout preserves opposing fruit words, incompatible varieties and contrary net quantities as vetoes. The layout on a shared nutrition table can remain ambiguous, and the photo-level evidence does not establish that two trade items with indistinguishable artwork can be separated.

## Rebuild

Use the repository's pinned OpenCV and Pillow versions with the Grocery Store Dataset archive at revision `fc80ba90f803d79d0383df52c5a4ac5de99ff6fc`. The builder checks the SHA-256 of each source before extracting features. Reacquire the historical files into a cache and pass the directories containing ID-named originals.

```bash
python scripts/fetch_recognition_photos.py /tmp/pack-sources --cohort prior
python scripts/fetch_recognition_photos.py /tmp/pack-sources --cohort new
python scripts/evaluate_fresh_size.py fetch /tmp/pack-sources/size
PYTHONPATH=src python scripts/build_registered_pack_gallery.py \
  /path/to/GroceryStoreDataset.zip /tmp/pack-sources/prior/blind \
  /tmp/pack-sources/new/blind /tmp/pack-sources/size
```

The Python package compresses the same JSON bytes that the browser loads. The shared gallery SHA-256 is `2004df3c9792873b8260d23e71b9e454de230b278b4651326b9110dbea23cb1b`.

## Source records

The source ledger identifies the original bytes, view, GTIN or off-registry class, panel coordinates, and original image URL or archive member. Coordinates use the listed longest-edge scale after applying EXIF orientation. The orange ingredient photograph also receives a 90-degree clockwise rotation before enrollment.

- Official training image provenance and roles are in [training.csv](../grocery-catalogue/training.csv). The photographs are by the Grocery Store Dataset authors. [Dataset](https://github.com/marcusklasson/GroceryStoreDataset)
- The GMX and NX records identify the suppliers or contributors, original links and applicable image terms. [Historical sources](../new-photos/rows.csv)
- The SZ records include the licensor, contributor and original image URLs. [Package-size sources](../fresh-size-eval/labels.csv)
- The gallery stores image features. Open Food Facts contributor photographs used in enrollment carry the [CC BY-SA 3.0 licence](https://creativecommons.org/licenses/by-sa/3.0/). The original photographs and packaging artwork retain their respective rights.
