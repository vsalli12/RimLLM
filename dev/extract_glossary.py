
import os
import pathlib
import xml.etree.ElementTree as ET
import xmltodict
import json
GLOSSARY_PATH = pathlib.Path(__file__).with_name("glossary_total.json")

def getGlossary(path_to_game = "C:/Program Files (x86)/Steam/steamapps/common/RimWorld/Data"):

    # Travers all the branch of a specified path
    glossary = {}
    def_tags = set()
    for DLC in os.listdir(path_to_game):
        pathDLC = pathlib.Path(path_to_game, DLC)
        if not os.path.isdir(pathDLC): # Non directory
            continue
        defs = pathlib.Path(pathDLC, "defs")
        if not os.path.exists(defs): # No definitions
            continue

        for root, dirs, files in os.walk(defs):
            for x in files:
                p = pathlib.Path(root, x)
                if not os.path.exists(p):
                    print(p)

                glossary_entries = read_xml(p)

                if glossary_entries:
                    glossary.update(glossary_entries)
    
    GLOSSARY_PATH.write_text(json.dumps(glossary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Glossary extracted!")
    print(len(glossary), "items")
                

def read_xml(path):

    with open(path, "r", encoding="UTF-8") as f:
        xml_raw = f.read()
    try:
        xml_d = xmltodict.parse(xml_raw)
    except:
        print("errored on:")
        print(xml_raw)

    defs = xml_d["Defs"]
    if not defs:
        return
    glossary = {}

    skiptags = ("RecipeDef", "StatDef", "RecordDef", "SpecialThingFilterDef", "MainButtonDef", "KeyBindingCategoryDef", "DifficultyDef",
                "StorytellerDef", "AnomalyPlaystyleDef", "ScenPartDef", "IdeoPresetCategoryDef", "PreceptDef")

    for def_tag, items in defs.items():
        if def_tag in skiptags:
            continue

        if isinstance(items, dict):
            items = [items]

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            label = item.get("label")
            description = item.get("description")
            if not label or not description:
                continue

            existing = glossary.get(label)
            if existing and existing["defTag"] == "ThingDef":
                continue

            glossary[label] = {
                "description": description,
                "defName": item.get("defName"),
                "defTag": def_tag,
            }
        return glossary

if __name__ == "__main__":
    getGlossary()