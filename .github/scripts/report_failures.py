"""Turn failed JUnit test cases into GitHub annotations, readable from the public API without logging in."""
import glob
import sys
import xml.etree.ElementTree as ET

shown = 0
for pattern in sys.argv[1:]:
    for path in glob.glob(pattern, recursive=True):
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            continue
        for case in root.iter("testcase"):
            for problem in list(case.findall("failure")) + list(case.findall("error")):
                name = f"{case.get('classname', '')}.{case.get('name', '')}"
                text = (problem.get("message") or "") + "\n" + (problem.text or "")
                text = text.strip()[-1500:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
                print(f"::error title={name}::{text}")
                shown += 1
                if shown >= 9:
                    sys.exit(0)
if not shown:
    print("::error title=Nessun test fallito nei report::Controlla il log del passo (errore di build o di avvio).")
