"""Turn failed JUnit test cases into GitHub annotations, readable from the public API without logging in."""
import glob
import sys
import xml.etree.ElementTree as ET


def annotation(text, limit):
    return text.strip()[-limit:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")


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
                print(f"::error title={name}::{annotation((problem.get('message') or '') + chr(10) + (problem.text or ''), 1500)}")
                output = chr(10).join(part.text or "" for part in case.findall("system-out") + case.findall("system-err"))
                lines = [line for line in output.splitlines() if line.strip()]
                if lines:
                    print(f"::warning title=Output di {name}::{annotation(chr(10).join(lines[-40:]), 3000)}")
                shown += 1
                if shown >= 9:
                    sys.exit(0)
if not shown:
    print("::error title=Nessun test fallito nei report::Controlla il log del passo (errore di build o di avvio).")
