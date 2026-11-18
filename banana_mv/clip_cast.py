"""27B-only authorization helpers for picture bindings and first appearances.

Reference images identify people; they do not grant anyone permission to enter
an arbitrary clip. Story authority stays with Python's current local event.
"""
import re
from banana_mv.commission_guard import role_pictures
from banana_mv.core import map_image_mentions


PICTURE = re.compile(r"^\s*<Picture\s+(\d+)>\s*(?:[=:：＝|｜-]\s*)?(.*)$", re.I)
ROLE = re.compile(r"^\s*\[?\s*(S[12])\s*\]?\s*(?:[=:：＝|｜-]\s*)?(.*)$", re.I)
TIME = re.compile(r"(?<!\d)(\d{1,2}):(\d\d)\.(\d{1,3})(?!\d)")
FIRST = re.compile(r"(?:首次|第一次).{0,22}(?:入鏡|登場|出現|露面)|(?:first|initial)\s+(?:appear|entrance|on.screen)|(?:debut)", re.I)
PRESENT_REF = re.compile(r"<Picture\s+(\d+)>", re.I)
ROLE_REF = re.compile(r"<Subject\s+([12])>|\b(S[12])\b", re.I)


def _name(text):
    """Extract only a clearly named identity, not costume or a performance rule."""
    value = re.split(r"[,，;；(（|｜\n]", text, 1)[0].strip(" \t=：:－-。")
    if not value or value.startswith("<") or len(value) > 48:
        return ""
    if re.search(r"\b(?:male|female|adult|sing|lyrics|lead)\b", value, re.I):
        return ""
    return re.sub(r"\s+", "", value).casefold()


def explicit_bindings(brief, count):
    """Resolve only author-named S1/S2↔Picture pairs; never infer from order."""
    text = map_image_mentions(str(brief or ""), count)
    direct = role_pictures(text)
    images, names = {}, {}
    for line in text.splitlines():
        p = PICTURE.match(line)
        if p and 1 <= int(p[1]) <= count:
            name = _name(p[2])
            if name:
                images.setdefault(name, set()).add(int(p[1]))
        s = ROLE.match(line)
        if s:
            name = _name(s[2])
            if name:
                names[s[1].upper()] = name
    for role, name in names.items():
        if role in direct:
            continue
        choices = images.get(name, ())
        if len(choices) == 1:
            direct[role] = f"<Picture {next(iter(choices))}>"
    return direct


def first_appearances(brief):
    """Find only explicitly time-anchored 'S1 first appears' instructions.

    Never guess first appearance from SRT, cast listing, or a character's first
    mention. Requires a time header and an explicit first-entrance declaration.
    """
    lines = str(brief or "").splitlines()
    result = {}
    for i, line in enumerate(lines):
        stamp = TIME.search(line)
        if not stamp:
            continue
        # A nearby performance sentence owns this time; never borrow the
        # next timestamp block's first-entrance event.
        rows = [line]
        for following in lines[i+1:i+4]:
            if TIME.search(following):
                break
            rows.append(following)
        neighborhood = " ".join(rows)
        for role in ("S1", "S2"):
            if not re.search(r"\b" + role + r"\b", neighborhood, re.I):
                continue
            if not FIRST.search(neighborhood):
                continue
            # Require the role and the first-appearance word in one sentence
            # (not a separate sentence about the other singer).
            for part in re.split(r"[。！？.!?\n]", neighborhood):
                if re.search(r"\b" + role + r"\b", part, re.I) and FIRST.search(part):
                    minutes, seconds, millis = stamp.groups()
                    time_sec = int(minutes)*60 + int(seconds) + int(millis.ljust(3,"0"))/1000
                    result[role] = min(time_sec, result.get(role, float("inf")))
    return result


def clip_visibility(event, brief, segment, pictures, cues):
    """Return bounded access for explicitly anchored roles; not a cast guess."""
    start = float(segment["start"])
    duration = float(segment["seconds"])
    entrances = first_appearances(brief)
    visible_roles = {role for cue in cues for role in cue.get("subjects", ())}
    # The allocator is supposed to put active cast references in THIS CLIP.
    # Use that as extra positive permission, never global image availability.
    active_refs = {int(n) for n in PRESENT_REF.findall(event)}
    for role, pic in pictures.items():
        p = PRESENT_REF.search(pic)
        if p and int(p[1]) in active_refs:
            visible_roles.add(role)
        # Local event may explicitly name a singer role without a Picture tag.
        if re.search(r"\b" + role + r"\b", event, re.I):
            visible_roles.add(role)
    access = {}
    for role in ("S1", "S2"):
        if role in entrances and entrances[role] >= start+duration-0.0005:
            access[role] = {"status": "absent", "reason": "not yet introduced by the authored timeline"}
        elif role in entrances and start < entrances[role] < start+duration:
            access[role] = {"status": "entry", "at": round(entrances[role]-start, 3)}
        elif active_refs and role not in visible_roles:
            access[role] = {"status": "absent", "reason": "not in this clip's active cast"}
        else:
            access[role] = {"status": "available"}
    return access


def visibility_lines(access):
    out = []
    for role, number in (("S1", 1), ("S2", 2)):
        state = access[role]
        if state["status"] == "absent":
            out.append(f"<Subject {number}> ({role}) REFERENCE ONLY: not in the image, "
                       "not a background observer, silhouette, reflection or cutaway.")
        elif state["status"] == "entry":
            out.append(f"<Subject {number}> ({role}) FIRST APPEARS at exactly "
                       f"{state['at']:.3f}s within this clip; entirely offscreen before that.")
        else:
            out.append(f"<Subject {number}> ({role}) may appear only when the "
                       "current clip event stages this actor. An uploaded image alone is not a scene.")
    return out


def premature_cast_errors(blocks, access, slots=()):
    """Reject absent cast, including shots ending before a timed first entrance."""
    errors = {}
    by_number = {row["number"]: row for row in slots}
    for role, number in (("S1", 1), ("S2", 2)):
        state = access[role]
        if state["status"] not in ("absent", "entry"):
            continue
        mention = re.compile(r"<Subject\s+"+str(number)+r">", re.I)
        for shot, body in blocks.items():
            slot = by_number.get(shot)
            premature = state["status"] == "absent" or (
                state["status"] == "entry" and slot and
                float(slot["end"]) <= float(state["at"]) + 0.001
            )
            if premature and mention.search(body):
                errors.setdefault(shot, []).append(
                    f"[ERROR][PrematureCast] [Shot {shot}] <Subject {number}> ({role}) "
                    "must remain offscreen until its authorized first appearance. "
                    "Remove this actor from the shot, including reactions, background "
                    "and reflections; preserve the authorized ongoing event and camera.")
    return errors
