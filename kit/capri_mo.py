"""Mass Override in the Capri package: every player runs every cast (1.16.17).

The two scripts (template/mass-override/, the repo's game/r6/scripts copies) are put into the package a server
hands out, with that server's own gate in them: XyberRP Staging talks to /mass-override-staging/, XyberRP to
/mass-override/ -- the only difference between the two packages' copies, with the label the cast log prints and
the build every report names.  Pure Python, no I/O but the two templates.
"""
from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
O77 = "r6/scripts/Open77/Open77MassOverride.reds"
CAPRI = "r6/scripts/CapriPersonalityConstruct/Capri.MassOverride.reds"
TEMPLATES = {O77: os.path.join(HERE, "template", "mass-override", "Open77MassOverride.reds"),
             CAPRI: os.path.join(HERE, "template", "mass-override", "Capri.MassOverride.reds")}
STAGING_BASE = "https://xyberrp.duckdns.org/mass-override-staging"
BASES = {"staging": (STAGING_BASE, "staging"), "production": ("https://xyberrp.duckdns.org/mass-override", "production")}
BASE_LINE = 'public static func Base() -> String { return "%s"; }'
LABEL_LINE = 'public static func Label() -> String { return "%s"; }'
BUILD_LINE = 'public static func Version() -> String { return "%s"; }'
VERSION_RX = re.compile(r"^\d{1,4}(\.\d{1,4}){1,4}$")


class MoError(Exception):
    pass


def render(role: str, version: str) -> dict[str, bytes]:
    """The two scripts for ROLE's package (UTF-8, LF), with its gate, its label and the package's version."""
    if role not in BASES:
        raise MoError(f"no gate for {role!r}")
    if not VERSION_RX.match(version or ""):
        raise MoError(f"the version {version!r} is not N.N.N")
    base, label = BASES[role]
    out = {}
    for path, tpl in TEMPLATES.items():
        text = open(tpl, encoding="utf-8").read().replace("\r\n", "\n")
        out[path] = text
    o = out[O77]
    for what, line, new in (("gate", BASE_LINE % STAGING_BASE, BASE_LINE % base),
                            ("label", LABEL_LINE % "staging", LABEL_LINE % label)):
        if o.count(line) != 1:
            raise MoError(f"the Mass Override template's {what} line is there {o.count(line)} times")
        o = o.replace(line, new)
    builds = re.findall(re.escape(BUILD_LINE.split('"')[0]) + r'"([^"]*)"; \}', o)
    if len(builds) != 1:
        raise MoError("the Mass Override template's build line is not there exactly once")
    o = o.replace(BUILD_LINE % builds[0], BUILD_LINE % version)
    out[O77] = o
    # every address in it is the role's gate's (the URLs are built from Base())
    if role == "production" and "mass-override-staging" in o:
        raise MoError("the production copy still names the staging gate")
    if "class MassOverrideRemote" not in o or "MassOverrideApply.Targets" not in out[CAPRI]:
        raise MoError("the templates are not the ones where every player runs every cast")
    return {p: t.encode("utf-8") for p, t in out.items()}


def values(o77: bytes) -> dict:
    """What a package's Open77MassOverride.reds says: its gate, label, build, and whether everyone runs a cast."""
    text = o77.decode("utf-8", errors="replace")
    out = {}
    for key, line in (("base", BASE_LINE), ("label", LABEL_LINE), ("build", BUILD_LINE)):
        m = re.search(re.escape(line.split('"')[0]) + r'"([^"]*)"; \}', text)
        out[key] = m.group(1) if m else None
    out["everyone"] = "class MassOverrideRemote" in text
    return out
