#!/usr/bin/env python3
# Apply additive detection enhancements to OUI-SPY Unified Blue.
#
# Target: src/raw/detector.cpp
# Adds:
# - Generic BLE service-data UUID + payload-prefix filter type
# - ASTM/OpenDroneID FFFA:0D preset
# - Flock Safety BLE multi-signature preset
# Existing persisted filter IDs 0..5 are preserved; the new type is 6.

from pathlib import Path
import argparse
import shutil
import sys

MARKER = "OUI-SPY ENHANCED SERVICE-DATA PATCH 2026-10-01"

def fail(msg):
    raise RuntimeError(msg)

def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        fail("%s: expected exactly 1 anchor, found %d" % (label, n))
    return text.replace(old, new, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    src = repo / "src" / "raw" / "detector.cpp"
    if not src.exists():
        fail("Not found: %s" % src)

    text = src.read_text(encoding="utf-8")
    if MARKER in text:
        print("[+] Enhancement patch already applied.")
        return 0

    backup = src.with_suffix(".cpp.pre-enhanced.bak")
    if not backup.exists():
        shutil.copy2(src, backup)

    text = replace_once(
        text,
        '''    FT_META_COMPOSITE  = 5,
};''',
        '''    FT_META_COMPOSITE  = 5,
    // Generic BLE Service Data matcher. Identifier syntax is "UUID16:HEX_PREFIX",
    // for example "FFFA:0D" for ASTM/OpenDroneID Remote ID. Appended at 6 so
    // persisted filter values 0-5 remain backwards-compatible.
    FT_SERVICE_DATA_PREFIX = 6,
};''',
        "filter enum"
    )

    text = replace_once(
        text,
        '''        case FT_META_COMPOSITE:  return "META";
    }''',
        '''        case FT_META_COMPOSITE:    return "META";
        case FT_SERVICE_DATA_PREFIX: return "SDAT";
    }''',
        "filter badge code"
    )

    text = replace_once(
        text,
        '#define DETECTOR_FW_VERSION "1.1.0"',
        '#define DETECTOR_FW_VERSION "1.2.0-enhanced"',
        "detector version"
    )

    text = replace_once(
        text,
        '''#define BLE_MM_META_COMPOSITE "meta_composite"
#define BLE_MM_UNKNOWN        "unknown"''',
        '''#define BLE_MM_META_COMPOSITE "meta_composite"
#define BLE_MM_SERVICE_DATA   "service_data"
#define BLE_MM_UNKNOWN        "unknown"''',
        "BLE match-method label"
    )

    text = replace_once(
        text,
        '''            } else if (rawType <= FT_META_COMPOSITE) {''',
        '''            } else if (rawType <= FT_SERVICE_DATA_PREFIX) {''',
        "NVS filter-type upper bound"
    )

    helper_anchor = '''// Forward declaration — defined below; FT_META_COMPOSITE filters defer to it.
bool matchesMetaComposite(NimBLEAdvertisedDevice* dev, const char*& outLabel);
'''
    helper_code = r'''// Forward declaration — defined below; FT_META_COMPOSITE filters defer to it.
bool matchesMetaComposite(NimBLEAdvertisedDevice* dev, const char*& outLabel);

// OUI-SPY ENHANCED SERVICE-DATA PATCH 2026-10-01
// Match a 16-bit BLE Service Data UUID plus an arbitrary byte-prefix.
// Identifier syntax: "UUID16:HEX_PREFIX" (example: "FFFA:0D").
// This is generic so future signatures can use the same engine.
static bool serviceUuidMatches16(const NimBLEUUID& uuid, const String& target) {
    String s = uuid.toString().c_str();
    s.toLowerCase();
    String t = normalizeHexId(target);
    return (s.length() == 4 && s.equals(t)) ||
           (s.length() >= 8 && s.substring(4, 8).equals(t));
}

static bool matchesServiceDataPrefix(NimBLEAdvertisedDevice* dev,
                                     const String& identifier,
                                     uint16_t* outUuid = nullptr) {
    if (!dev || !dev->haveServiceData()) return false;

    int sep = identifier.indexOf(':');
    if (sep <= 0 || sep >= (int)identifier.length() - 1) return false;

    String uuidPart = normalizeHexId(identifier.substring(0, sep));
    String prefix   = normalizeHexId(identifier.substring(sep + 1));
    if (uuidPart.length() != 4 || prefix.length() == 0 || (prefix.length() & 1)) {
        return false;
    }

    const size_t wantedBytes = prefix.length() / 2;
    for (uint8_t i = 0; i < dev->getServiceDataCount(); i++) {
        NimBLEUUID uuid = dev->getServiceDataUUID(i);
        if (!serviceUuidMatches16(uuid, uuidPart)) continue;

        std::string data = dev->getServiceData(i);
        if (data.size() < wantedBytes) continue;

        bool ok = true;
        for (size_t b = 0; b < wantedBytes; b++) {
            String byteHex = prefix.substring(b * 2, b * 2 + 2);
            uint8_t wanted = (uint8_t)strtoul(byteHex.c_str(), nullptr, 16);
            if ((uint8_t)data[b] != wanted) {
                ok = false;
                break;
            }
        }
        if (ok) {
            if (outUuid) *outUuid = (uint16_t)strtoul(uuidPart.c_str(), nullptr, 16);
            return true;
        }
    }
    return false;
}
'''
    text = replace_once(text, helper_anchor, helper_code, "service-data helper")

    resolve_old = '''            case FT_META_COMPOSITE: {
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) {
                    outType = f.type; outIdent = f.identifier; return true;
                }
                break;
            }
'''
    resolve_new = '''            case FT_SERVICE_DATA_PREFIX: {
                if (matchesServiceDataPrefix(dev, f.identifier)) {
                    outType = f.type; outIdent = f.identifier; return true;
                }
                break;
            }
            case FT_META_COMPOSITE: {
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) {
                    outType = f.type; outIdent = f.identifier; return true;
                }
                break;
            }
'''
    text = replace_once(text, resolve_old, resolve_new, "resolve matcher")

    target_old = '''            case FT_META_COMPOSITE: {
                // Installed via the META preset; defer to the composite
                // matcher. The label it returns ("META-RAYBAN (mfr+svc)" /
                // "META-RAYBAN (name)") is more informative than the filter
                // description, so it wins.
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) {
                    matchedDescription = metaLabel;
                    return true;
                }
                break;
            }
'''
    target_new = '''            case FT_SERVICE_DATA_PREFIX: {
                if (matchesServiceDataPrefix(dev, filter.identifier)) {
                    matchedDescription = filter.description;
                    return true;
                }
                break;
            }
            case FT_META_COMPOSITE: {
                // Installed via the META preset; defer to the composite
                // matcher. The label it returns ("META-RAYBAN (mfr+svc)" /
                // "META-RAYBAN (name)") is more informative than the filter
                // description, so it wins.
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) {
                    matchedDescription = metaLabel;
                    return true;
                }
                break;
            }
'''
    text = replace_once(text, target_old, target_new, "target matcher")

    classify_old = '''            case FT_META_COMPOSITE: {
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) return BLE_MM_META_COMPOSITE;
                break;
            }
'''
    classify_new = '''            case FT_SERVICE_DATA_PREFIX: {
                uint16_t svc = 0;
                if (matchesServiceDataPrefix(dev, filter.identifier, &svc)) {
                    outServiceUuid = svc;
                    return BLE_MM_SERVICE_DATA;
                }
                break;
            }
            case FT_META_COMPOSITE: {
                const char* metaLabel = nullptr;
                if (matchesMetaComposite(dev, metaLabel)) return BLE_MM_META_COMPOSITE;
                break;
            }
'''
    text = replace_once(text, classify_old, classify_new, "BLE classifier")

    preset_anchor = '''static const size_t PRESET_AXON_COUNT = sizeof(PRESET_AXON) / sizeof(PRESET_AXON[0]);
'''
    preset_insert = '''static const size_t PRESET_AXON_COUNT = sizeof(PRESET_AXON) / sizeof(PRESET_AXON[0]);

// Flock Safety BLE signals used by Mode 1 Detector. Mode 3 Flock-You remains
// unchanged and continues to provide its dedicated Wi-Fi detection pipeline.
static const PresetEntry PRESET_FLOCK[] = {
    { FT_MAC_PREFIX,     "B41E52",         "Flock Safety IEEE OUI" },
    { FT_COMPANY_ID,     "09C8",           "XUNTONG manufacturer ID observed in Flock/Penguin BLE" },
    { FT_NAME_SUBSTRING, "FS Ext Battery", "Flock external-battery advertised name" },
    { FT_NAME_SUBSTRING, "FlockCam",       "Flock camera advertised name" },
    { FT_NAME_SUBSTRING, "Pigvision",      "Flock/Pigvision advertised name" },
    { FT_NAME_SUBSTRING, "Penguin-",       "Flock Penguin legacy advertised-name prefix" },
};
static const size_t PRESET_FLOCK_COUNT = sizeof(PRESET_FLOCK) / sizeof(PRESET_FLOCK[0]);

// ASTM F3411 / Open Drone ID BLE Service Data:
// UUID 0xFFFA (ASTM Remote ID) + application code 0x0D (Open Drone ID).
// This remains identifiable even when the advertiser uses a randomized MAC.
static const PresetEntry PRESET_REMOTE_ID[] = {
    { FT_SERVICE_DATA_PREFIX, "FFFA:0D", "ASTM Remote ID service data UUID 0xFFFA + Open Drone ID app code 0x0D" },
};
static const size_t PRESET_REMOTE_ID_COUNT = sizeof(PRESET_REMOTE_ID) / sizeof(PRESET_REMOTE_ID[0]);
'''
    text = replace_once(text, preset_anchor, preset_insert, "presets")

    text = replace_once(
        text,
        '''        .sig-meta { color: #e94560; }
        .sig-sep  { color: #6b6b7d; }''',
        '''        .sig-meta { color: #e94560; }
        .sig-sdat { color: #4dd0e1; }
        .sig-sep  { color: #6b6b7d; }''',
        "signature CSS"
    )

    text = replace_once(
        text,
        '''                .match-badge.type-META { color: #e94560; }
''',
        '''                .match-badge.type-META { color: #e94560; }
                .match-badge.type-SDAT { color: #4dd0e1; }
''',
        "match badge CSS"
    )

    flock_old = '''                    <summary><b>FLOCK SAFETY</b> <code>1 OUI</code></summary>
                    <div class="oui-entries"><code>B4:1E:52</code></div>
                    <button type="button" class="oui-add-btn" onclick="appendOUIs('B4:1E:52')">+ Add to filter list</button>
                    <div class="oui-meta"><strong>Category:</strong> Automated License Plate Reader (ALPR) / Security Camera</div>
                    <div class="oui-meta"><strong>Detection Range:</strong> WiFi/Cellular</div>
                    <div class="oui-meta"><strong>Common Devices:</strong> Flock Safety Camera, Falcon Camera, Raven Camera</div>
'''
    flock_new = '''                    <summary><b>FLOCK SAFETY</b> <code>multi-signature</code></summary>
                    <div class="oui-entries"><code>B4:1E:52</code> <code>CID 0x09C8</code> <code>names: FS Ext Battery / FlockCam / Pigvision / Penguin-</code></div>
                    <button type="button" class="oui-add-btn" onclick="addVendor('flock','FLOCK SAFETY','B4:1E:52')">+ Add all BLE signatures</button>
                    <div class="oui-meta"><strong>Category:</strong> Automated License Plate Reader (ALPR) / Security Camera</div>
                    <div class="oui-meta"><strong>Detection Range:</strong> BLE/WiFi range</div>
                    <div class="oui-meta"><strong>Common Devices:</strong> Flock Safety Camera, Falcon, Penguin accessories</div>
'''
    text = replace_once(text, flock_old, flock_new, "Flock UI")

    skydio_tail = '''                    <div class="oui-meta"><strong>Common Devices:</strong> Skydio 2, Skydio X2, Skydio 3</div>
                    </details>
                    <!-- OUI_DB_END -->
'''
    rid_card = '''                    <div class="oui-meta"><strong>Common Devices:</strong> Skydio 2, Skydio X2, Skydio 3</div>
                    </details>
                    <details>
                    <summary><b>DRONE REMOTE ID</b> <code>ASTM/OpenDroneID BLE</code></summary>
                    <div class="oui-entries"><code>Service Data UUID 0xFFFA</code> <code>App Code 0x0D</code></div>
                    <button type="button" class="oui-add-btn" onclick="addVendor('remoteid','DRONE REMOTE ID', null)">+ Add Remote ID signature</button>
                    <div class="oui-meta"><strong>Category:</strong> Standards-based Drone Remote ID</div>
                    <div class="oui-meta"><strong>Detection:</strong> BLE Service Data; independent of manufacturer OUI or randomized MAC</div>
                    <div class="oui-note">Matches the standardized ASTM Remote ID UUID plus the Open Drone ID application code. It identifies a Remote ID broadcast, not a specific drone brand.</div>
                    </details>
                    <!-- OUI_DB_END -->
'''
    text = replace_once(text, skydio_tail, rid_card, "Remote ID UI")

    js_old = '''            var VENDOR_OUIS = {
                axon:   '00:25:DF'
            };
            var VENDOR_LABELS = { axon: 'AXON', meta: 'META / RAY-BAN' };
'''
    js_new = '''            var VENDOR_OUIS = {
                axon:   '00:25:DF',
                flock:  'B4:1E:52'
            };
            var VENDOR_LABELS = {
                axon: 'AXON',
                meta: 'META / RAY-BAN',
                flock: 'FLOCK SAFETY',
                remoteid: 'DRONE REMOTE ID'
            };
'''
    text = replace_once(text, js_old, js_new, "vendor maps")

    sigs_old = '''            var VENDOR_SIGS = {
                axon:   [ {t:'cid',  v:'0x034D', l:'CID'},
                          {t:'uuid', v:'0xFC81', l:'UUID'} ],
                meta:   [ {t:'meta', v:'0x0D53+0xFD5F', l:'COMPOSITE'} ]
            };
'''
    sigs_new = '''            var VENDOR_SIGS = {
                axon:   [ {t:'cid',  v:'0x034D', l:'CID'},
                          {t:'uuid', v:'0xFC81', l:'UUID'} ],
                meta:   [ {t:'meta', v:'0x0D53+0xFD5F', l:'COMPOSITE'} ],
                flock:  [ {t:'cid',  v:'0x09C8', l:'CID'},
                          {t:'name', v:'FS Ext Battery', l:'NAME'},
                          {t:'name', v:'FlockCam', l:'NAME'},
                          {t:'name', v:'Pigvision', l:'NAME'},
                          {t:'name', v:'Penguin-', l:'NAME'} ],
                remoteid:[ {t:'sdat', v:'0xFFFA + 0x0D', l:'SERVICE DATA'} ]
            };
'''
    text = replace_once(text, sigs_old, sigs_new, "signature maps")

    apply_old = '''        if (presetName == "axon") {
            label = "Axon body cam";
            added = applyPreset(PRESET_AXON, PRESET_AXON_COUNT, "Axon body cam");
        } else if (presetName == "meta") {
            label = "Meta glasses";
            added = applyPreset(PRESET_META, PRESET_META_COUNT, "Meta glasses");
        } else {
'''
    apply_new = '''        if (presetName == "axon") {
            label = "Axon body cam";
            added = applyPreset(PRESET_AXON, PRESET_AXON_COUNT, "Axon body cam");
        } else if (presetName == "meta") {
            label = "Meta glasses";
            added = applyPreset(PRESET_META, PRESET_META_COUNT, "Meta glasses");
        } else if (presetName == "flock") {
            label = "Flock Safety";
            added = applyPreset(PRESET_FLOCK, PRESET_FLOCK_COUNT, "Flock Safety");
        } else if (presetName == "remoteid") {
            label = "Drone Remote ID";
            added = applyPreset(PRESET_REMOTE_ID, PRESET_REMOTE_ID_COUNT, "Drone Remote ID");
        } else {
'''
    text = replace_once(text, apply_old, apply_new, "apply endpoint")

    remove_old = '''        if (n == "axon")           removed = removePreset(PRESET_AXON, PRESET_AXON_COUNT);
        else if (n == "meta")      removed = removePreset(PRESET_META, PRESET_META_COUNT);
        else { request->send(400, "application/json", "{\\"ok\\":false,\\"error\\":\\"unknown preset\\"}"); return; }
'''
    remove_new = '''        if (n == "axon")           removed = removePreset(PRESET_AXON, PRESET_AXON_COUNT);
        else if (n == "meta")      removed = removePreset(PRESET_META, PRESET_META_COUNT);
        else if (n == "flock")     removed = removePreset(PRESET_FLOCK, PRESET_FLOCK_COUNT);
        else if (n == "remoteid")  removed = removePreset(PRESET_REMOTE_ID, PRESET_REMOTE_ID_COUNT);
        else { request->send(400, "application/json", "{\\"ok\\":false,\\"error\\":\\"unknown preset\\"}"); return; }
'''
    text = replace_once(text, remove_old, remove_new, "remove endpoint")

    status_old = '''        String body = "{\\"axon\\":";
        body += presetInstalled(PRESET_AXON, PRESET_AXON_COUNT) ? "true" : "false";
        body += ",\\"meta\\":";
        body += presetInstalled(PRESET_META, PRESET_META_COUNT) ? "true" : "false";
        body += "}";
'''
    status_new = '''        String body = "{\\"axon\\":";
        body += presetInstalled(PRESET_AXON, PRESET_AXON_COUNT) ? "true" : "false";
        body += ",\\"meta\\":";
        body += presetInstalled(PRESET_META, PRESET_META_COUNT) ? "true" : "false";
        body += ",\\"flock\\":";
        body += presetInstalled(PRESET_FLOCK, PRESET_FLOCK_COUNT) ? "true" : "false";
        body += ",\\"remoteid\\":";
        body += presetInstalled(PRESET_REMOTE_ID, PRESET_REMOTE_ID_COUNT) ? "true" : "false";
        body += "}";
'''
    text = replace_once(text, status_old, status_new, "status endpoint")

    text = text.replace(
        "// POST body/query: name=axon | meta",
        "// POST body/query: name=axon | meta | flock | remoteid",
        1
    )

    src.write_text(text, encoding="utf-8")

    checks = [
        "FT_SERVICE_DATA_PREFIX = 6",
        'return "SDAT"',
        "matchesServiceDataPrefix",
        '"FFFA:0D"',
        "PRESET_FLOCK",
        "PRESET_REMOTE_ID",
        "remoteid: 'DRONE REMOTE ID'",
        MARKER,
    ]
    for c in checks:
        if c not in text:
            fail("post-patch sanity check missing: %s" % c)

    print("[+] Patched:", src)
    print("[+] Backup :", backup)
    print("[+] Generic BLE service-data matching enabled.")
    print("[+] Remote ID FFFA:0D preset added.")
    print("[+] Flock BLE multi-signature preset added.")
    print("[+] Existing filter IDs 0..5 preserved; new type = 6.")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("[-] PATCH FAILED:", e, file=sys.stderr)
        sys.exit(1)
