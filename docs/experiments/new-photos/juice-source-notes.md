# Independent juice image source collection

Sealed on 2026-11-24 before recognizer scoring. The raw-image SHA-256 values and blind IDs appear in blind.csv. The labels.csv joins those IDs to sources, exact identity, family and provenance. Only the blind directory and blind.csv are model inputs. Files are unmodified source bytes. The images are frozen for local evaluation. Publish the reference rows and hashes. The 29 Open Food Facts uploads include contributor handles, product links and CC BY-SA 3.0 details. Publicly accessible non-OFF publisher images have no identified open redistribution licence.

## Cohort

35 candidates, 16 GTINs, 19 source groups. 29 Open Food Facts original uploads carry upload times between 2014-05-17 and 2026-08-31. The remaining images comprise five retail or food-service packshots and one manufacturer scene. Repeated consumer views of one Open Food Facts GTIN are conservatively one source group. A source group is a clustered provenance unit. It cannot establish the number of physical containers. The 23 front views, 11 reverse/ingredient views and one contextual scene are labeled individually.

- 7 originals carry one of the three registered Swedish GTINs. Their views are two whole packshot fronts, one whole front in a photographed scene, and four reverse/ingredient views. Each registered flavour has one fresh visible-front candidate before the independent perceptual screen.
- 18 same-brand, same-flavour, different-GTIN images come from independently verified Finnish market or alternate-size products. Their exact truth is UNKNOWN. Their family_truth gives the flavour comparison.
- 10 images show unregistered products, including other God Morgon flavour blends and other-brand apple and orange drinks. Their exact and family truth are UNKNOWN.

The OFF product records identify the SKU for ingredient/back views even when branding or flavour is absent from the image. This evidence supports test identity and is withheld from inference. The sample contains independently uploaded still photos and curated publisher media. One hand-held alternate-size orange pack was photographed in a store aisle. Studio packshots and repeated home/retail views differ from normal store photography.

## Screening and exclusions

Original byte hashes were compared with every image file in the pinned GroceryStoreDataset archive and all seven old external specimens. Duplicate SHA or duplicate records are fatal. Before sealing, visual comparison excluded K-Ruoka's three old front packshots (same original GroceryStore iconic composition), manufacturer white-flap apple/orange, and multiple retail reproductions across ICA, Martin & Servera, Dabas, Natmat, Onfos and Torebrings. Recorded articles without verified photographs were excluded. Official/cross-collection near-duplicate adjudication for final scoring is owned independently by the evaluation script and may reduce the eligible count.

Swedish OFF orange #2 and mix #1 were seen in the prior external set. Swedish apple #1 matches the old iconic. Orange/mixture snapshots that repeated the same framing, and unidentifiable nutrition or recycling-only crops, were excluded. Alternate GTINs came from verifiable retailer/producer listings. The six earliest raw uploads for Joker were screened to keep broad control sourcing proportionate. Only images meeting the predeclared crop/duplicate rules were retained. Other Swedish and Finnish candidates were screened at native-upload level. Each dated field indicates when OFF received a file.

## Reproducing source bytes

For ordinary numeric OFF images and public packshots, GET the exact image_url in labels.csv and compare bytes to sha256. The OFF public S3 archive was enumerated for numeric original uploads. Named selected-front images and size variants were excluded. AWS object LastModified is a storage sync time. Upload dates come from the OFF API. The archive listing and product metadata snapshots live under sources/ for local audit. Many publisher media endpoints can replace an image at the same URL. Report byte drift and never substitute a new picture silently.

For the publisher PDF scene, fetch the PDF at its image_url. Verify PDF SHA-256 61f2734152cef76d5910f4923da68c0de20d43129b40f0ce21d59ab5a969d720. Physical PDF page 8 (printed pages 14–15) contains the orange 1L food-service listing, its GTIN and the intact scene. Verify before writing the original embedded JPEG with PyMuPDF.

    from pathlib import Path
    import fitz
    from hashlib import sha256

    source = Path("eckes_sortimentsbroschyr_2025-v2_high.pdf").read_bytes()
    assert sha256(source).hexdigest() == "61f2734152cef76d5910f4923da68c0de20d43129b40f0ce21d59ab5a969d720"
    with fitz.open(stream=source, filetype="pdf") as document:
        assert 607 in {entry[0] for entry in document[7].get_images(full=True)}
        jpeg = document.extract_image(607)["image"]
    assert sha256(jpeg).hexdigest() == "d03141e8696f584c60a4d9cd82e78a5194f49dd0f5d507e1de9983f6180d47e9"
    Path("NX-d03141e8696f584c.jpg").write_bytes(jpeg)

The original full raster has 1713×647 pixels. Printed 1L is visible on the depicted carton. Its opaque background is retained. The brochure’s entire page and other product imagery are outside this specimen.
