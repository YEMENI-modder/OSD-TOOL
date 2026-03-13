"""
OSD Tool for Resident Evil 4
By: اليمني

Usage:
  osd_tool.exe <file.OSD>     → يسأل: استخراج أو ريباك
  osd_tool.exe <Data.txt>     → ريباك مباشرة (ملف جديد)
  osd_tool.exe <BIO4.EXE>     → تركيب أكواد OSD
  osd_tool.exe extract        → يسأل عن المسار
  osd_tool.exe repack         → يسأل عن المسار
  osd_tool.exe patch          → يسأل عن المسار
"""

import os
import sys
import struct

MAGIC     = bytes([0x44, 0x69, 0x73, 0x63])
FALSE_HDR = bytes([0x00, 0x00, 0x00, 0x00])
FOOTER    = bytes([0xCD, 0xCD, 0xCD, 0xCD])


# ══════════════════════════════════════════════════════
#  مساعدات
# ══════════════════════════════════════════════════════

def split_values(s):
    s = s.replace("،", " ").replace(",", " ")
    return [x for x in s.split() if x]

def join_values(vals):
    return ", ".join(str(v) for v in vals)

def pause():
    input("\n  اضغط Enter للخروج... / Press Enter to exit...")


# ══════════════════════════════════════════════════════
#  قراءة / كتابة بلوك
# ══════════════════════════════════════════════════════

def read_block_body(data, pos):
    try:
        aev = data[pos]; pos += 1
        n   = data[pos]; pos += 1
        items, qtys = [], []
        for _ in range(n):
            items.append(struct.unpack_from('<H', data, pos)[0]); pos += 2
            qtys.append(struct.unpack_from('<H', data, pos)[0]);  pos += 2
        nsf  = data[pos]; pos += 1
        suc  = list(data[pos:pos+nsf]); pos += nsf
        fail = list(data[pos:pos+nsf]); pos += nsf
        return aev, items, qtys, nsf, suc, fail, pos
    except:
        return None

def make_block(op, aev, items, qtys, nsf, suc, fail):
    return {"osd_op": op, "aev_index": aev, "items": items,
            "quantities": qtys, "num_sf": nsf,
            "success_aevs": suc, "fail_aevs": fail}

def block_to_bytes(b):
    buf = bytearray()
    buf += MAGIC if b["osd_op"] else FALSE_HDR
    buf.append(b["aev_index"])
    buf.append(len(b["items"]))
    for item, qty in zip(b["items"], b["quantities"]):
        buf += struct.pack('<H', item)
        buf += struct.pack('<H', qty)
    buf.append(b["num_sf"])
    buf += bytes(b["success_aevs"])
    buf += bytes(b["fail_aevs"])
    return bytes(buf)


# ══════════════════════════════════════════════════════
#  تحليل OSD ثنائي
# ══════════════════════════════════════════════════════

def parse_osd_file(raw):
    data = raw.rstrip(b'\xCD')
    first = data.find(MAGIC)
    if first == -1:
        return []

    true_blocks = []
    p = first
    while True:
        idx = data.find(MAGIC, p)
        if idx == -1: break
        res = read_block_body(data, idx + 4)
        if res is None: p = idx + 4; continue
        aev, items, qtys, nsf, suc, fail, end = res
        tb = make_block(True, aev, items, qtys, nsf, suc, fail)
        tb["file_offset"] = idx
        tb["file_size"]   = end - idx
        true_blocks.append((idx, end, tb))
        p = idx + 4

    if not true_blocks:
        return []

    all_blocks = []
    for i, (t_start, t_end, tb) in enumerate(true_blocks):
        if tb["aev_index"] != 0 or len(tb["items"]) != 0:
            all_blocks.append(tb)
        zone_start = t_end
        zone_end   = true_blocks[i+1][0] if i+1 < len(true_blocks) else len(data)
        zone = data[zone_start:zone_end]
        zp = 0
        while zp + 4 <= len(zone):
            res = read_block_body(zone, zp + 4)
            if res is None: zp += 1; continue
            aev, items, qtys, nsf, suc, fail, new_zp = res
            if aev == 0 and len(items) == 0: zp = new_zp; continue
            fb = make_block(False, aev, items, qtys, nsf, suc, fail)
            fb["file_offset"] = zone_start + zp
            fb["file_size"]   = new_zp - zp
            all_blocks.append(fb)
            zp = new_zp

    return all_blocks


# ══════════════════════════════════════════════════════
#  تحليل Data.txt
# ══════════════════════════════════════════════════════

def parse_txt(content):
    lines   = content.splitlines()
    num_osd = None
    blocks  = []
    current = None
    for line in lines:
        line = line.strip()
        if not line or "=" not in line: continue
        key, _, val = line.partition("=")
        key = key.strip().upper(); val = val.strip()
        if key == "NUMBER OF OSD":
            if val.isdigit(): num_osd = int(val)
        elif key == "OSD OPERATION":
            if current is not None: blocks.append(current)
            current = {"OSD OPERATION": val.upper()}
        elif current is not None:
            current[key] = val
    if current is not None: blocks.append(current)
    if num_osd is None: num_osd = len(blocks)
    return num_osd, blocks

def txt_to_block(b):
    op   = b.get("OSD OPERATION", "TRUE") == "TRUE"
    aev  = int(b.get("AEV INDEX", "00"), 16)
    items = [int(x, 16) for x in split_values(b.get("ITEM NUMBER", "")) if x]
    qtys  = [int(q) for q in split_values(b.get("NUMBER OF QUANTITY", ""))]
    while len(qtys) < len(items): qtys.append(65535)
    nsf  = int(b.get("NUMBER OF SUCCESS AND FAILURE", "0") or "0")
    suc  = [int(x, 16) for x in split_values(b.get("AEV SUCCESS",  "")) if x]
    fail = [int(x, 16) for x in split_values(b.get("AEV FAILURE",  "")) if x]
    suc  = (suc  + [0xFF]*nsf)[:nsf]
    fail = (fail + [0xFF]*nsf)[:nsf]
    return make_block(op, aev, items, qtys, nsf, suc, fail)


# ══════════════════════════════════════════════════════
#  EXT
# ══════════════════════════════════════════════════════

def do_extract(osd_path):
    osd_path = osd_path.strip().strip('"')
    if not os.path.exists(osd_path):
        print(f"\n  [خطأ] الملف غير موجود: {osd_path}")
        return False

    with open(osd_path, "rb") as f:
        raw = f.read()

    blocks = parse_osd_file(raw)
    if not blocks:
        print("\n  [خطأ] ما فيه بلوكات OSD في الملف")
        return False

    folder  = os.path.splitext(os.path.basename(osd_path))[0]
    out_dir = os.path.join(os.path.dirname(os.path.abspath(osd_path)), folder)
    os.makedirs(out_dir, exist_ok=True)

    lines = [f"NUMBER OF OSD = {len(blocks)}"]
    for b in blocks:
        lines.append("")
        lines.append(f"OSD Operation = {'True' if b['osd_op'] else 'False'}")
        lines.append(f"AEV INDEX = {b['aev_index']:02X}")
        lines.append(f"Number OF ITEM = {len(b['items'])}")
        lines.append(f"Item Number = {join_values([f'{i:X}' for i in b['items']])}")
        lines.append(f"Number of Quantity = {join_values([str(q) for q in b['quantities']])}")
        lines.append(f"Number of Success and Failure = {b['num_sf']}")
        lines.append(f"AEV Success = {join_values([f'{a:02X}' for a in b['success_aevs']])}")
        lines.append(f"AEV Failure = {join_values([f'{a:02X}' for a in b['fail_aevs']])}")

    txt_path = os.path.join(out_dir, "Data.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n  [OK] تم الاستخراج - {len(blocks)} بلوك")
    print(f"  المجلد : {out_dir}")
    print(f"  الملف  : Data.txt")
    print()
    print(f"  {'#':<4} {'Operation':<10} {'AEV':>5}  Items")
    print(f"  {'─'*50}")
    for i, b in enumerate(blocks):
        op  = "TRUE " if b["osd_op"] else "FALSE"
        itm = ", ".join(f"{x:X}" for x in b["items"])
        print(f"  [{i+1:02d}] {op}     AEV={b['aev_index']:02X}  [{itm}]")
    return True


# ══════════════════════════════════════════════════════
#  REPACK طريقة 1 - ملف جديد (من Data.txt)
# ══════════════════════════════════════════════════════

def do_repack_new(txt_path, add_footer=None):
    txt_path = txt_path.strip().strip('"')
    if not os.path.exists(txt_path):
        print(f"\n  [خطأ] الملف غير موجود: {txt_path}")
        return False

    txt_dir  = os.path.dirname(os.path.abspath(txt_path))
    base     = os.path.basename(txt_dir)
    osd_path = os.path.join(os.path.dirname(txt_dir), f"{base}.OSD")

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()

    num_osd, raw_blocks = parse_txt(content)
    count = min(num_osd, len(raw_blocks))

    buf = bytearray()
    for i in range(count):
        buf += block_to_bytes(txt_to_block(raw_blocks[i]))

    # لو ما اتحدد من الخارج، اسأل
    if add_footer is None:
        print()
        while True:
            ans = input("  تبي تضيف CD CD CD CD في النهاية؟ [y/n] : ").strip().lower()
            if ans in ("y", "n"): break
        add_footer = (ans == "y")

    if add_footer:
        buf += FOOTER

    with open(osd_path, "wb") as f:
        f.write(buf)

    print(f"\n  [OK] تم التجميع - ملف جديد")
    print(f"  الملف    : {osd_path}")
    print(f"  البلوكات : {count}")
    print(f"  الحجم    : {len(buf)} bytes")
    return True


# ══════════════════════════════════════════════════════
#  REPACK طريقة 2 - تحديث الأصلي (من OSD مباشرة)
# ══════════════════════════════════════════════════════

def do_repack_inplace(osd_path):
    osd_path = osd_path.strip().strip('"')
    base     = os.path.splitext(os.path.basename(osd_path))[0]
    osd_dir  = os.path.dirname(os.path.abspath(osd_path))
    txt_path = os.path.join(osd_dir, base, "Data.txt")

    if not os.path.exists(txt_path):
        print(f"\n  [خطأ] ما لقيت مجلد '{base}' أو Data.txt بداخله")
        print(f"  المتوقع : {txt_path}")
        return False

    with open(txt_path, "r", encoding="utf-8") as f:
        content = f.read()
    with open(osd_path, "rb") as f:
        raw = bytearray(f.read())

    num_osd, raw_blocks = parse_txt(content)
    count = min(num_osd, len(raw_blocks))

    has_footer = raw[-4:] == bytearray(FOOTER)
    if has_footer: raw = raw[:-4]

    orig_blocks = parse_osd_file(bytes(raw))
    written = 0; size_added = 0

    for i in range(count):
        if i >= len(orig_blocks): break
        orig     = orig_blocks[i]
        file_off = orig["file_offset"] + size_added
        orig_sz  = orig["file_size"]
        new_bytes = block_to_bytes(txt_to_block(raw_blocks[i]))
        new_sz   = len(new_bytes)
        extra    = new_sz - orig_sz

        if extra <= 0:
            raw[file_off : file_off + new_sz] = new_bytes
            if extra < 0:
                raw[file_off + new_sz : file_off + orig_sz] = bytes(-extra)
        else:
            after    = bytes(raw[file_off + orig_sz:])
            tail     = after.rstrip(b'\x00')
            trailing = len(after) - len(tail)
            new_after = tail + bytes(trailing - extra) if trailing >= extra else tail
            raw = bytearray(raw[:file_off]) + bytearray(new_bytes) + bytearray(new_after)
            size_added += extra

        written += 1

    if has_footer: raw += bytearray(FOOTER)

    with open(osd_path, "wb") as f:
        f.write(raw)

    print(f"\n  [OK] تم التحديث في الملف الأصلي")
    print(f"  الملف    : {osd_path}")
    print(f"  البلوكات : {written} محدثة")
    if size_added:
        print(f"  زيادة    : +{size_added} bytes في النهاية")
    return True


# ══════════════════════════════════════════════════════
#  PATCH
# ══════════════════════════════════════════════════════

PATCH_FIND     = bytes.fromhex("81A0CC5200007FFFFFFFE84850D4")
PATCH_REPL     = bytes.fromhex("E9892E00009090909090E84850D4")
PATCH_FP1_OFF  = 0x002C6D88
PATCH_FP1_DATA = bytes.fromhex("81A0CC5200007FFFFFFF608B98344F000085DB7439813BCDCDCDCD7431813B44697363740343EBED8D5B040FB60B50515251E8C5A3D3FF83C4045A598BC85885C974E28D904027D1FF895140EBD761E928D1FFFF")
PATCH_FP2_OFF  = 0x00568A20
PATCH_FP2_DATA = bytes.fromhex(
    "608B82F4272F008138CDCDCDCD0F84F30000008138446973637403"
    "40EBE9""0FB64E363A480475F4""8D40050FB61831C9""0FB7748801"
    "0FB77C8803""505152""8D8A3441300056E89A58AAFF"
    "5A6681FFFFFF74096639F80F829D000000""595841""39D972CF"
    "31C90FB7748801""0FB77C8803""5051528D8A344130006A0156E84B22AAFF"
    "5A5A6681FFFFFF7421""663B78027D09662978026631FFEB1A"
    "662B780250515250E966000000""5A5958EB0885C075EE5958EB0759586685FF75B6"
    "4139D97CA7""0FB67C98018D44980285FF743E"
    "0FB67438FF50535756E88E86A9FF""5E85C07415F640340175046A01EB026A00"
    "56E84F90A9FF83C4085F5B584FEBCE""59580FB67C98018D4498028D0438EBBE"
    "61C3""E81FCDA9FFE84C96A9FFEB8E"
)

def do_patch(exe_path):
    exe_path = exe_path.strip().strip('"')
    if not os.path.exists(exe_path):
        print(f"\n  [خطأ] الملف غير موجود: {exe_path}")
        return False

    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    print()
    ok = 0; err = 0

    idx = data.find(PATCH_FIND)
    if idx == -1:
        if data.find(PATCH_REPL) != -1:
            print("  [--] التعديل 1: موجود مسبقاً")
        else:
            print("  [خطأ] التعديل 1: ما لقيت البايتات"); err += 1
    else:
        data[idx : idx+len(PATCH_REPL)] = PATCH_REPL
        print("  [OK] التعديل 1 (Change to): تم"); ok += 1

    if PATCH_FP1_OFF + len(PATCH_FP1_DATA) > len(data):
        print(f"  [خطأ] التعديل 2: الملف أصغر من المتوقع"); err += 1
    else:
        data[PATCH_FP1_OFF : PATCH_FP1_OFF+len(PATCH_FP1_DATA)] = PATCH_FP1_DATA
        print(f"  [OK] التعديل 2 (0x{PATCH_FP1_OFF:08X}): تم"); ok += 1

    if PATCH_FP2_OFF + len(PATCH_FP2_DATA) > len(data):
        print(f"  [خطأ] التعديل 3: الملف أصغر من المتوقع"); err += 1
    else:
        data[PATCH_FP2_OFF : PATCH_FP2_OFF+len(PATCH_FP2_DATA)] = PATCH_FP2_DATA
        print(f"  [OK] التعديل 3 (0x{PATCH_FP2_OFF:08X}): تم"); ok += 1

    if err > 0:
        print(f"\n  [!] {err} خطأ - الملف ما اتحفظ")
        return False

    with open(exe_path, "wb") as f:
        f.write(data)
    print(f"\n  [OK] تم تطبيق {ok} تعديل وحفظ الملف")
    print(f"  الملف : {exe_path}")
    return True


# ══════════════════════════════════════════════════════
#  نقطة الدخول الرئيسية
# ══════════════════════════════════════════════════════

def main():
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║     OSD Tool — Resident Evil 4           ║")
    print("  ║     By: اليمني                           ║")
    print("  ╚══════════════════════════════════════════╝")

    # ── وضع BAT: بدون args، ينتظر إدخال يدوي ──
    if len(sys.argv) == 1:
        print()
        print("  اسحب ملف على هذا البرنامج أو")
        print("  استخدم أحد ملفات BAT المرفقة")
        print()
        pause()
        return

    # ── arg[1] = الوضع (extract/repack/patch) ──
    mode = sys.argv[1].lower()

    # مجلد الـ EXE نفسه
    exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))

    # ── وضع BAT: extract ──
    if mode == "extract":
        print()
        print("  --- استخراج OSD → Data.txt ----------------")
        osds = [f for f in os.listdir(exe_dir) if f.lower().endswith(".osd")]
        if not osds:
            print(f"  [!] ما لقيت أي ملف OSD في المجلد:")
            print(f"      {exe_dir}")
            pause(); return
        print(f"  وجدت {len(osds)} ملف OSD في المجلد\n")
        ok_count = 0
        for name in osds:
            path = os.path.join(exe_dir, name)
            print(f"  ► {name}")
            if do_extract(path):
                ok_count += 1
            print()
        print(f"  {'─'*45}")
        print(f"  اكتملت العملية: {ok_count}/{len(osds)} ملف")
        pause(); return

    # ── وضع BAT: repack (ملف جديد من Data.txt) ──
    if mode == "repack":
        print()
        print("  --- تجميع Data.txt → OSD ------------------")
        # يدور Data.txt في المجلدات الفرعية
        txts = []
        for entry in os.scandir(exe_dir):
            if entry.is_dir():
                txt = os.path.join(entry.path, "Data.txt")
                if os.path.exists(txt):
                    txts.append(txt)
        if not txts:
            print(f"  [!] ما لقيت أي مجلد يحتوي Data.txt في:")
            print(f"      {exe_dir}")
            pause(); return
        print(f"  وجدت {len(txts)} ملف Data.txt\n")

        # اختيار الطريقة
        print("  [1] ملف جديد (بدون أصفار)")
        print("  [2] تحديث الملف الأصلي (يحافظ على الهيكل والأصفار)")
        print()
        while True:
            rp_mode = input("  اختر الطريقة [1/2] : ").strip()
            if rp_mode in ("1", "2"): break
            print("  [!] اكتب 1 أو 2")
        print()

        # سؤال Footer مرة واحدة للكل (طريقة 1 فقط)
        add_footer = False
        if rp_mode == "1":
            while True:
                ans = input("  تبي تضيف CD CD CD CD في النهاية لكل الملفات؟ [y/n] : ").strip().lower()
                if ans in ("y", "n"): break
            add_footer = (ans == "y")
        print()

        ok_count = 0
        for txt_path in txts:
            folder = os.path.basename(os.path.dirname(txt_path))
            print(f"  ► {folder}\\Data.txt")
            if rp_mode == "1":
                if do_repack_new(txt_path, add_footer=add_footer):
                    ok_count += 1
            else:
                # طريقة 2: OSD بجانب المجلد
                osd_path = os.path.join(exe_dir, f"{folder}.OSD")
                if not os.path.exists(osd_path):
                    print(f"  [!] ما لقيت الملف الأصلي: {folder}.OSD")
                else:
                    if do_repack_inplace(osd_path):
                        ok_count += 1
            print()
        print(f"  {'─'*45}")
        print(f"  اكتملت العملية: {ok_count}/{len(txts)} ملف")
        pause(); return

    # ── وضع BAT: patch ──
    if mode == "patch":
        print()
        print("  --- تركيب أكواد OSD في BIO4.EXE -----------")
        exes = [f for f in os.listdir(exe_dir) if f.lower() == "bio4.exe"]
        if not exes:
            print(f"  [!] ما لقيت BIO4.EXE في المجلد:")
            print(f"      {exe_dir}")
            pause(); return
        path = os.path.join(exe_dir, exes[0])
        print(f"  ► {exes[0]}\n")
        do_patch(path)
        pause(); return

    # ── وضع Drag & Drop: arg[1] = مسار الملف ──
    file_path = sys.argv[1].strip().strip('"')

    if not os.path.exists(file_path):
        print(f"\n  [خطأ] الملف غير موجود:\n  {file_path}")
        pause()
        return

    name = os.path.basename(file_path).lower()
    ext  = os.path.splitext(file_path)[1].lower()

    print(f"\n  الملف : {os.path.basename(file_path)}")
    print()

    # ── BIO4.EXE → patch مباشرة ──
    if name == "bio4.exe":
        print("  تم التعرف على BIO4.EXE - سيتم تركيب أكواد OSD")
        print()
        do_patch(file_path)
        pause()
        return

    # ── Data.txt → repack جديد مباشرة ──
    if name == "data.txt":
        print("  تم التعرف على Data.txt - سيتم إنشاء ملف OSD جديد")
        print()
        do_repack_new(file_path)
        pause()
        return

    # ── OSD → يسأل: استخراج أو ريباك ──
    if ext == ".osd":
        print("  تم التعرف على ملف OSD")
        print()
        print("  [1] استخراج  →  Data.txt")
        print("  [2] تجميع    →  تحديث الأصلي (يحتاج مجلد Data.txt بجانبه)")
        print()
        while True:
            choice = input("  اختر [1/2] : ").strip()
            if choice in ("1", "2"): break
            print("  [!] اكتب 1 أو 2")

        if choice == "1":
            do_extract(file_path)
        else:
            do_repack_inplace(file_path)
        pause()
        return

    # ── نوع غير معروف ──
    print(f"  [!] نوع غير معروف: {ext}")
    print()
    print("  الأنواع المدعومة:")
    print("  • .OSD  → استخراج أو تجميع")
    print("  • Data.txt → تجميع ملف جديد")
    print("  • BIO4.EXE → تركيب أكواد")
    pause()


if __name__ == "__main__":
    main()
