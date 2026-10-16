import os
import shutil
import hashlib
import zipfile
from xml.etree import ElementTree

SCRIPT_VERSION = 2
KODI_VERSIONS = ["krypton", "leia", "matrix", "nexusrepo", "omega", "repo"]
IGNORE = [".git", ".github", ".gitignore", ".DS_Store", "thumbs.db", ".idea", "venv"]

def _setup_colors():
    return os.environ.get("TERM") is not None and os.environ.get("TERM") != "dumb"

_COLOR_ESCAPE = "\x1b[{}m"
_COLORS = {
    "black": "30", "red": "31", "green": "4;32", "yellow": "3;33",
    "blue": "34", "magenta": "35", "cyan": "1;36", "grey": "37", "endc": "0"
}
_SUPPORTS_COLOR = _setup_colors()

def color_text(text, color):
    return '{}{}{}'.format(_COLOR_ESCAPE.format(_COLORS[color]), text, _COLOR_ESCAPE.format(_COLORS["endc"])) if _SUPPORTS_COLOR else text

def convert_bytes(num):
    for x in ['bytes', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

class Generator:
    def __init__(self, release):
        self.release_path = release
        self.zips_path = os.path.join(self.release_path, "repo", "zips") # Matches your GitHub XML Layout folder structure
        addons_xml_path = os.path.join(self.zips_path, "addons.xml")
        md5_path = os.path.join(self.zips_path, "addons.xml.md5")

        if not os.path.exists(self.zips_path):
            os.makedirs(self.zips_path)

        self._remove_binaries()

        if self._generate_addons_file(addons_xml_path):
            print("Successfully updated {}".format(color_text(addons_xml_path, 'yellow')))
            if self._generate_md5_file(addons_xml_path, md5_path):
                print("Successfully updated {}".format(color_text(md5_path, 'yellow')))

    def _remove_binaries(self):
        for parent, dirnames, filenames in os.walk(self.release_path):
            for fn in filenames:
                if fn.lower().endswith("pyo") or fn.lower().endswith("pyc"):
                    compiled = os.path.join(parent, fn)
                    try:
                        os.remove(compiled)
                        print("Removed compiled python file: {}".format(color_text(compiled, 'green')))
                    except:
                        print("Failed to remove compiled python file: {}".format(color_text(compiled, 'red')))
            for dir in dirnames:
                if "pycache" in dir.lower():
                    compiled = os.path.join(parent, dir)
                    try:
                        shutil.rmtree(compiled)
                        print("Removed __pycache__ cache folder: {}".format(color_text(compiled, 'green')))
                    except:
                        print("Failed to remove __pycache__ cache folder:  {}".format(color_text(compiled, 'red')))

    def _create_zip(self, folder, addon_id, version):
        addon_folder = os.path.join(self.release_path, folder)
        zip_folder = os.path.join(self.zips_path, addon_id)
        if not os.path.exists(zip_folder):
            os.makedirs(zip_folder)

        final_zip = os.path.join(zip_folder, "{0}-{1}.zip".format(addon_id, version))
        if not os.path.exists(final_zip):
            zip = zipfile.ZipFile(final_zip, "w", compression=zipfile.ZIP_DEFLATED)
            root_len = len(os.path.dirname(os.path.abspath(addon_folder)))

            for root, dirs, files in os.walk(addon_folder):
                # FIXED: Safely modify directory and file listings without skipping items
                dirs[:] = [d for d in dirs if d not in IGNORE]
                files = [f for f in files if not any(f.startswith(i) for i in IGNORE)]

                archive_root = os.path.abspath(root)[root_len:]
                for f in files:
                    fullpath = os.path.join(root, f)
                    archive_name = os.path.join(archive_root, f)
                    zip.write(fullpath, archive_name, zipfile.ZIP_DEFLATED)

            zip.close()
            size = convert_bytes(os.path.getsize(final_zip))
            print("Zip created for {} ({}) - {}".format(color_text(addon_id, 'cyan'), color_text(version, 'green'), color_text(size, 'yellow')))

    def _copy_meta_files(self, addon_id, addon_folder):
        tree = ElementTree.parse(os.path.join(self.release_path, addon_id, "addon.xml"))
        root = tree.getroot()
        copyfiles = ["addon.xml"]
        for ext in root.findall("extension"):
            if ext.get("point") in ["xbmc.addon.metadata", "kodi.addon.metadata"]:
                assets = ext.find("assets")
                if not assets is None:
                    for art in [a for a in assets if a.text]:
                        copyfiles.append(os.path.normpath(art.text))

        src_folder = os.path.join(self.release_path, addon_id)
        for file in copyfiles:
            addon_path = os.path.join(src_folder, file)
            if not os.path.exists(addon_path): continue
            zips_path = os.path.join(addon_folder, file)
            asset_path = os.path.split(zips_path)[0]
            if not os.path.exists(asset_path):
                os.makedirs(asset_path)
            shutil.copy(addon_path, zips_path)

    def _generate_addons_file(self, addons_xml_path):
        if not os.path.exists(addons_xml_path):
            addons_root = ElementTree.Element('addons')
            addons_xml = ElementTree.ElementTree(addons_root)
        else:
            addons_xml = ElementTree.parse(addons_xml_path)
            addons_root = addons_xml.getroot()

        folders = [i for i in os.listdir(self.release_path) if os.path.isdir(os.path.join(self.release_path, i)) and i != "repo" and not i.startswith(".") and os.path.exists(os.path.join(self.release_path, i, "addon.xml"))]
        addon_xpath = "addon[@id='{}']"
        changed = False
        found_ids = []

        for addon in folders:
            try:
                addon_xml_path = os.path.join(self.release_path, addon, "addon.xml")
                addon_xml = ElementTree.parse(addon_xml_path)
                addon_root = addon_xml.getroot()
                
                # FIXED: Automatically strips out the illegal name tag from all extension blocks
                for ext in addon_root.findall("extension"):
                    if ext.get("name") is not None:
                        del ext.attrib["name"]
                        
                id = addon_root.get('id')
                version = addon_root.get('version')
                found_ids.append(id)

                updated = False
                addon_entry = addons_root.find(addon_xpath.format(id))
                
                if addon_entry is not None:
                    if addon_entry.get('version') != version:
                        addons_root.remove(addon_entry)
                        addons_root.append(addon_root)
                        updated = True
                        changed = True
                else:
                    addons_root.append(addon_root)
                    updated = True
                    changed = True

                if updated:
                    self._create_zip(addon, id, version)
                    self._copy_meta_files(addon, os.path.join(self.zips_path, id))
            except Exception as e:
                print("Failed to process addon {}: {}".format(color_text(addon, 'red'), e))

        for addon_entry in addons_root.findall('addon'):
            if addon_entry.get('id') not in found_ids:
                addons_root.remove(addon_entry)
                changed = True

        if changed or not os.path.exists(addons_xml_path):
            addons_root[:] = sorted(addons_root, key=lambda child: child.get('id'))
            try: ElementTree.indent(addons_xml, space="    ", level=0)
            except AttributeError: pass
            addons_xml.write(addons_xml_path, encoding='utf-8', xml_declaration=True, short_empty_elements=True)
            return True
        return False

    def _generate_md5_file(self, addons_xml_path, md5_path):
        try:
            with open(addons_xml_path, 'rb') as f:
                data = f.read()
            md5_hash = hashlib.md5(data).hexdigest()
            with open(md5_path, 'w', encoding='utf-8') as f:
                f.write(md5_hash)
            return True
        except Exception as e:
            print("Failed to generate MD5: {}".format(e))
            return False

if __name__ == "__main__":
    Generator(os.getcwd())

