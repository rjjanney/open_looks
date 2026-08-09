"""Generate ground-truth values from the real scripts/xmp_importer.py for
port/xmp_importer.test.mjs to check the JS port against. Run with any
Python that can import scripts/ (no cv2/numpy needed here, unlike
gen_fixtures.py):

    python port/gen_xmp_fixtures.py

Writes port/xmp_fixtures.json.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from xmp_importer import load_xmp_file, parse_xmp_bytes  # noqa: E402

fixtures = {"realFiles": [], "synthetic": []}

# Every real .xmp fixture already in the repo (used to calibrate
# develop_engine.py -- see the calibration_workflow memory) doubles as
# ground truth for the parser too.
xmp_dir = REPO_ROOT / "Source" / "LR_EXPORT_AND_LOOKS"
for path in sorted(xmp_dir.glob("*.xmp")):
    recipe = load_xmp_file(path)
    fixtures["realFiles"].append({
        "filename": path.name,
        "text": path.read_text(encoding="utf-8"),
        "expected": recipe,
    })

# None of the real fixtures exercise a tone-curve Seq or the warning paths
# (ignored-scalar-default, local-adjustment, PointColors) -- synthetic
# cases for those, still parsed through the real Python module.
synthetic_cases = [
    (
        "tone_curve",
        """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Contrast2012="20">
   <crs:ToneCurvePV2012>
    <rdf:Seq>
     <rdf:li>0, 10</rdf:li>
     <rdf:li>128, 140</rdf:li>
     <rdf:li>255, 250</rdf:li>
    </rdf:Seq>
   </crs:ToneCurvePV2012>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>""",
    ),
    (
        "warnings",
        """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Temperature="15"
    crs:Exposure2012="0.5">
   <crs:PaintBasedCorrections>
    <rdf:Seq>
     <rdf:li>
      <rdf:Description crs:What="Correction"/>
     </rdf:li>
    </rdf:Seq>
   </crs:PaintBasedCorrections>
   <crs:PointColors>
    <rdf:Seq>
     <rdf:li>10, 0.5, 0.5, -1, -1, -1, -1, -1</rdf:li>
     <rdf:li>-1, -1, -1, -1, -1, -1, -1, -1</rdf:li>
    </rdf:Seq>
   </crs:PointColors>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>""",
    ),
    (
        "no_warnings_at_defaults",
        """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Temperature="0"
    crs:Contrast2012="10">
   <crs:PointColors>
    <rdf:Seq>
     <rdf:li>-1, -1, -1, -1, -1, -1, -1, -1</rdf:li>
    </rdf:Seq>
   </crs:PointColors>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>""",
    ),
]
for name, xml_text in synthetic_cases:
    recipe = parse_xmp_bytes(xml_text.encode("utf-8"), name)
    fixtures["synthetic"].append({"name": name, "text": xml_text, "expected": recipe})

out_path = Path(__file__).resolve().parent / "xmp_fixtures.json"
out_path.write_text(json.dumps(fixtures, indent=None))
print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
