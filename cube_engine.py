
"""
This Rubik's cube solver—originally written years ago and updated using GPT-6.1sol—takes color inputs via a 2D net layout and specializes in finding minimum-rotation solutions.
start : python gui_3d.py

"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rubiks_solver_final_with_step_net.py
원본에 다음 기능을 추가/수정함:
 - 매 스텝 이후에 큐브의 전개도(넷)를 콘솔에 출력
 - 전개도 출력용 보조 함수 display_net_state(faces, step)을 추가
 - print_solution_simple / print_solution_general에서 move를 적용한 후 전개도를 출력하게 함
 - 5스텝 단위 구분선은 기존과 동일하게 유지

사용법: 원본과 동일하게 실행하면, 각 스텝이 적용된 직후 콘솔에 현재 스티커 상태(전개도)가 출력됩니다.
"""

import sys
from collections import Counter

# ---------------- constants ----------------
FACE_ORDER = ['F','R','B','L','U','D']             # 입력 순서
KOCIEMBA_ORDER = ['U','R','F','D','L','B']    # kociemba 입력 순서
KOREAN_FACE_FULL = {'F':'앞(정면, F)','R':'오른쪽(R)','B':'뒤(B)','L':'왼쪽(L)','U':'윗면(U)','D':'아랫면(D)'}
ABS_POS_NAME = {'F':'앞','B':'뒤','L':'좌','R':'우','U':'위','D':'아래'}
ALLOWED = set("WYBGRO")
COLOR_NAME_KOR = {'W':'흰색','Y':'노란색','B':'파란색','G':'초록색','R':'빨간색','O':'주황색'}
ARROW = {'cw':'↻(시계)','ccw':'↺(반시계)','180':'⇄'}

# face -> canonical vector (for rotation mapping)
_FACE_VECTORS = {
    'F': (0,0,1),
    'B': (0,0,-1),
    'U': (0,1,0),
    'D': (0,-1,0),
    'R': (1,0,0),
    'L': (-1,0,0),
}

# ---------------- utility: input/menu/display ----------------
def print_main_menu():
    print("\n=== 루빅스 큐브 솔버 (최종판) ===")
    print("큐브 색상: W(흰) Y(노랑) B(파랑) G(초록) R(빨강) O(주황)")
    print("권장: 정면(F) 중앙이 흰색(W), 윗면(U) 중앙이 빨강(R) 상태에서 시작")
    print("1) 시작하기")
    print("2) 설명")
    print("3) 종료")

def show_explanation():
    print("""
설명(간단):
 - 입력 순서: 정면 -> 오른쪽 -> 뒷면 -> 왼쪽 -> 윗면 -> 아랫면
 - 각 면은 '왼쪽 위부터 오른쪽 아래' 순서로 9자(예: 123456789) 입력
 - 허용 색: W Y B G R O (대소문자 구분x)
 - 출력 버전 선택:
   • 심플: 간단히 표기 (예: Step 1: 위 ↺ (빨강) — 윗면을 바라보세요)
   • 일반: 시점 재배치 + 동작 안내 (상세)
 - 시점 방식(매 세션 선택):
   • 고정시점: 흰색을 정면, 빨강을 윗면으로 고정한 기준
   • 상대시점: 현재 보고 있는 면을 기준 (초기 기준은 입력한 정면)
""")

def input_menu_choice(prompt, choices):
    while True:
        c = input(prompt).strip()
        if c in choices:
            return c
        print(f"잘못된 입력입니다 — {', '.join(choices)} 중 하나를 입력하세요.")

def input_face(face_label):
    prompt = f"{KOREAN_FACE_FULL[face_label]} 배열 입력 (왼->오, 위->아래, 9글자): "
    while True:
        s = input(prompt)
        s = s.strip().replace(" ", "")
        if len(s) != 9:
            print("입력은 정확히 9글자여야 합니다. 예: WRGWRGWRG")
            continue
        s_up = s.upper()
        if not all(ch in ALLOWED for ch in s_up):
            print("허용 문자만 사용하세요: W Y B G R O (대소문자 가능).")
            continue
        return list(s_up)

def display_net_and_centers(faces):
    def rows(a): return [''.join(a[0:3]), ''.join(a[3:6]), ''.join(a[6:9])]
    U = rows(faces['U']); F = rows(faces['F']); R = rows(faces['R']); B = rows(faces['B']); L = rows(faces['L']); D = rows(faces['D'])
    pad = " " * 6
    print("\n입력된 큐브 넷 (각 문자 = 스티커):\n")
    for r in U: print(pad + " ".join(r))
    print()
    for i in range(3):
        print(" ".join(L[i]) + "    " + " ".join(F[i]) + "    " + " ".join(R[i]) + "    " + " ".join(B[i]))
    print()
    for r in D: print(pad + " ".join(r))
    print("\n면 중심 색 (센터):")
    for f in FACE_ORDER:
        c = faces[f][4]
        print(f" {KOREAN_FACE_FULL[f]} - {c} ({COLOR_NAME_KOR.get(c,'?')})")
    print()

def display_net_state(faces, step=None):
    def rows(a): return [a[0:3], a[3:6], a[6:9]]
    U = rows(faces['U']); F = rows(faces['F']); R = rows(faces['R']); B = rows(faces['B']); L = rows(faces['L']); D = rows(faces['D'])
    pad = " " * 6
    header = f"=== Step {step} 후 상태 ===" if step is not None else "=== 현재 상태 ==="
    print("\n" + header)
    for r in U:
        print(pad + " ".join(r))
    print()
    for i in range(3):
        print(" ".join(L[i]) + "    " + " ".join(F[i]) + "    " + " ".join(R[i]) + "    " + " ".join(B[i]))
    print()
    for r in D:
        print(pad + " ".join(r))
    centers = " | ".join(f"{f}:{faces[f][4]}" for f in FACE_ORDER)
    print("\n센터 요약: ", centers)
    print("\n")

# ---------------- kociemba conversion & solve ----------------
def build_kociemba_string(faces):
    color_to_face = {}
    for face in FACE_ORDER:
        center = faces[face][4]
        color_to_face[center] = face
    if len(color_to_face) != 6:
        raise ValueError("센터 색(중앙 스티커)이 6종류로 감지되지 않습니다. 각 면 중앙이 올바르게 입력되었는지 확인하세요.")
    out = []
    for face in KOCIEMBA_ORDER:
        stickers = faces[face]
        for col in stickers:
            mapped = color_to_face.get(col)
            if mapped is None:
                raise ValueError(f"알 수 없는 색 '{col}' — 중심 색과 매핑 실패.")
            out.append(mapped)
    return ''.join(out)

def safe_solve_with_kociemba(cube54):
    try:
        import kociemba
    except Exception:
        raise RuntimeError("kociemba 모듈이 없거나 불러올 수 없습니다. 'pip install kociemba' 후 재시도하세요.")
    return kociemba.solve(cube54)

def move_direction_text(suffix):
    if suffix == "": return "시계"
    if suffix == "'": return "반시계"
    if suffix == "2": return "180도"
    return suffix

# ---------------- rotations helpers (simulation) ----------------
def rotate_face_clockwise(face):
    return [face[6], face[3], face[0],
            face[7], face[4], face[1],
            face[8], face[5], face[2]]

def apply_move_to_faces(faces, mv):
    base = mv[0].upper()
    suffix = mv[1:] if len(mv) > 1 else ''
    if suffix == '': times = 1
    elif suffix == '2': times = 2
    elif suffix == "'": times = 3
    else: times = 1

    for _ in range(times):
        if base == 'U':
            faces['U'][:] = rotate_face_clockwise(faces['U'])
            tmp = faces['F'][0:3]
            faces['F'][0:3] = faces['R'][0:3]
            faces['R'][0:3] = faces['B'][0:3]
            faces['B'][0:3] = faces['L'][0:3]
            faces['L'][0:3] = tmp
        elif base == 'D':
            faces['D'][:] = rotate_face_clockwise(faces['D'])
            tmp = faces['F'][6:9]
            faces['F'][6:9] = faces['L'][6:9]
            faces['L'][6:9] = faces['B'][6:9]
            faces['B'][6:9] = faces['R'][6:9]
            faces['R'][6:9] = tmp
        elif base == 'F':
            faces['F'][:] = rotate_face_clockwise(faces['F'])
            tmp = [faces['U'][6], faces['U'][7], faces['U'][8]]
            faces['U'][6], faces['U'][7], faces['U'][8] = faces['L'][8], faces['L'][5], faces['L'][2]
            faces['L'][8], faces['L'][5], faces['L'][2] = faces['D'][2], faces['D'][1], faces['D'][0]
            faces['D'][2], faces['D'][1], faces['D'][0] = faces['R'][0], faces['R'][3], faces['R'][6]
            faces['R'][0], faces['R'][3], faces['R'][6] = tmp[0], tmp[1], tmp[2]
        elif base == 'B':
            faces['B'][:] = rotate_face_clockwise(faces['B'])
            tmp = [faces['U'][0], faces['U'][1], faces['U'][2]]
            faces['U'][0], faces['U'][1], faces['U'][2] = faces['R'][2], faces['R'][5], faces['R'][8]
            faces['R'][2], faces['R'][5], faces['R'][8] = faces['D'][8], faces['D'][7], faces['D'][6]
            faces['D'][8], faces['D'][7], faces['D'][6] = faces['L'][6], faces['L'][3], faces['L'][0]
            faces['L'][6], faces['L'][3], faces['L'][0] = tmp[0], tmp[1], tmp[2]
        elif base == 'R':
            faces['R'][:] = rotate_face_clockwise(faces['R'])
            tmp = [faces['U'][2], faces['U'][5], faces['U'][8]]
            faces['U'][2], faces['U'][5], faces['U'][8] = faces['F'][2], faces['F'][5], faces['F'][8]
            faces['F'][2], faces['F'][5], faces['F'][8] = faces['D'][2], faces['D'][5], faces['D'][8]
            faces['D'][2], faces['D'][5], faces['D'][8] = faces['B'][6], faces['B'][3], faces['B'][0]
            faces['B'][6], faces['B'][3], faces['B'][0] = tmp[0], tmp[1], tmp[2]
        elif base == 'L':
            faces['L'][:] = rotate_face_clockwise(faces['L'])
            tmp = [faces['U'][0], faces['U'][3], faces['U'][6]]
            faces['U'][0], faces['U'][3], faces['U'][6] = faces['B'][8], faces['B'][5], faces['B'][2]
            faces['B'][8], faces['B'][5], faces['B'][2] = faces['D'][0], faces['D'][3], faces['D'][6]
            faces['D'][0], faces['D'][3], faces['D'][6] = faces['F'][0], faces['F'][3], faces['F'][6]
            faces['F'][0], faces['F'][3], faces['F'][6] = tmp[0], tmp[1], tmp[2]

def apply_move_from_user_faces(faces, mv):
    worker = {f: faces[f][:] for f in FACE_ORDER}
    apply_move_to_faces(worker, mv)
    for f in FACE_ORDER:
        faces[f][:] = worker[f]

# ---------------- rotations: proper rotations generation ----------------
def gen_all_proper_rotations():
    import itertools
    perms = list(itertools.permutations([0,1,2], 3))
    signs = [(sx,sy,sz) for sx in (1,-1) for sy in (1,-1) for sz in (1,-1)]
    rots = []
    for p in perms:
        for s in signs:
            M = [[0]*3 for _ in range(3)]
            for i in range(3):
                M[i][p[i]] = s[i]
            det = (M[0][0]*(M[1][1]*M[2][2]-M[1][2]*M[2][1])
                   -M[0][1]*(M[1][0]*M[2][2]-M[1][2]*M[2][0])
                   +M[0][2]*(M[1][0]*M[2][1]-M[1][1]*M[2][0]))
            if det == 1:
                rots.append((p,s))
    return rots

_PROPER_ROTS = None

def transform_vector_by_rot(vec, rot):
    p, s = rot
    x = vec[p[0]] * s[0]
    y = vec[p[1]] * s[1]
    z = vec[p[2]] * s[2]
    return (x,y,z)

def build_relative_map_for_view(view_face):
    global _PROPER_ROTS
    if _PROPER_ROTS is None:
        _PROPER_ROTS = gen_all_proper_rotations()
    view_vec = _FACE_VECTORS[view_face]
    target = (0,0,1)
    chosen_rot = None
    for rot in _PROPER_ROTS:
        if transform_vector_by_rot(view_vec, rot) == target:
            chosen_rot = rot
            break
    mapping = {}
    for face, vec in _FACE_VECTORS.items():
        nv = transform_vector_by_rot(vec, chosen_rot)
        if nv == (0,0,1): mapping[face] = '앞'
        elif nv == (0,0,-1): mapping[face] = '뒤'
        elif nv == (1,0,0): mapping[face] = '우'
        elif nv == (-1,0,0): mapping[face] = '좌'
        elif nv == (0,1,0): mapping[face] = '위'
        elif nv == (0,-1,0): mapping[face] = '아래'
        else: mapping[face] = '?'
    return mapping

def build_fixed_map_by_colors(faces):
    color_to_face = {faces[f][4]: f for f in FACE_ORDER}
    face_W = color_to_face.get('W', None)
    face_R = color_to_face.get('R', None)
    if face_W is None or face_R is None:
        raise ValueError("고정좌표를 사용하려면 흰색(W)과 빨강(R) 센터가 필요합니다.")
    global _PROPER_ROTS
    if _PROPER_ROTS is None:
        _PROPER_ROTS = gen_all_proper_rotations()
    target_front = (0,0,1)
    target_up = (0,1,0)
    vec_W = _FACE_VECTORS[face_W]
    vec_R = _FACE_VECTORS[face_R]
    chosen = None
    for rot in _PROPER_ROTS:
        if transform_vector_by_rot(vec_W, rot) == target_front and transform_vector_by_rot(vec_R, rot) == target_up:
            chosen = rot
            break
    if chosen is None:
        return build_relative_map_for_view(face_W)
    mapping = {}
    for face, vec in _FACE_VECTORS.items():
        nv = transform_vector_by_rot(vec, chosen)
        if nv == (0,0,1): mapping[face] = '앞'
        elif nv == (0,0,-1): mapping[face] = '뒤'
        elif nv == (1,0,0): mapping[face] = '우'
        elif nv == (-1,0,0): mapping[face] = '좌'
        elif nv == (0,1,0): mapping[face] = '위'
        elif nv == (0,-1,0): mapping[face] = '아래'
        else: mapping[face] = '?'
    return mapping

# ---------------- printing: simple/general ----------------
def print_solution_simple(solution_str, faces, coord_mode, center_colors):
    print("\n=== 솔루션 (심플) ===")
    moves = solution_str.strip().split()
    fixed_map = build_fixed_map_by_colors(faces) if coord_mode == '1' else None
    current_view = 'F'
    rel_cache = {}
    for idx, mv in enumerate(moves, start=1):
        if idx != 1 and (idx-1) % 5 == 0:
            print("-----" * 5)
        base = mv[0].upper()
        suffix = mv[1:] if len(mv) > 1 else ''
        arrow = ARROW['cw'] if suffix=='' else (ARROW['ccw'] if suffix=="'" else ARROW['180'])

        if coord_mode == '1':
            pos = fixed_map.get(base, '?')
            pos_face_label = next((f_lbl for f_lbl, p in fixed_map.items() if p == pos), None)
        else:
            if current_view not in rel_cache:
                rel_cache[current_view] = build_relative_map_for_view(current_view)
            rel_map = rel_cache[current_view]
            pos = rel_map.get(base, '?')
            pos_face_label = next((f_lbl for f_lbl, p in rel_map.items() if p == pos), None)

        display_center_name = COLOR_NAME_KOR.get(center_colors.get(pos_face_label, '?'), '?') if pos_face_label else '?'
        print(f"Step {idx}: {pos} {arrow} ({display_center_name}) — {pos}을(를) 바라보세요")

        if pos_face_label:
            current_view = pos_face_label

        apply_move_from_user_faces(faces, mv)
        display_net_state(faces, step=idx)

def orient_instruction_from_current_to_target(current_view, target_face):
    rel = build_relative_map_for_view(current_view)
    pos = rel.get(target_face, '?')
    if pos == '앞': return "이미 해당 면을 보고 있습니다."
    if pos == '우': return "정면에서 큐브를 오른쪽으로 90° 회전하세요."
    if pos == '좌': return "정면에서 큐브를 왼쪽으로 90° 회전하세요."
    if pos == '뒤': return "큐브를 180° 돌려 해당 면이 앞으로 오게 하세요."
    if pos == '위': return "큐브를 뒤로 기울여 윗면이 보이게 하세요."
    if pos == '아래': return "큐브를 앞으로 기울여 아랫면이 보이게 하세요."
    return "해당 면을 보도록 회전하세요."

def print_solution_general(solution_str, faces, coord_mode, center_colors):
    print("\n=== 솔루션 (일반 — 상세) ===")
    moves = solution_str.strip().split()
    fixed_map = build_fixed_map_by_colors(faces) if coord_mode == '1' else None
    current_view = 'F'
    rel_cache = {}
    for idx, mv in enumerate(moves, start=1):
        if idx != 1 and (idx-1) % 5 == 0:
            print("-----" * 5)
        base = mv[0].upper()
        suffix = mv[1:] if len(mv) > 1 else ''
        dir_text = move_direction_text(suffix)
        arrow = ARROW['cw'] if suffix=='' else (ARROW['ccw'] if suffix=="'" else ARROW['180'])

        if coord_mode == '1':
            pos = fixed_map.get(base, '?')
            pos_face_label = next((f_lbl for f_lbl, p in fixed_map.items() if p == pos), None)
            orient_instr = f"시점(고정좌표): {pos}"
            rot_instr = orient_instruction_from_current_to_target(current_view, base)
        else:
            if current_view not in rel_cache:
                rel_cache[current_view] = build_relative_map_for_view(current_view)
            rel_map = rel_cache[current_view]
            pos = rel_map.get(base, '?')
            pos_face_label = next((f_lbl for f_lbl, p in rel_map.items() if p == pos), None)
            orient_instr = f"시점(상대좌표): '{pos}' 위치"
            rot_instr = orient_instruction_from_current_to_target(current_view, base)

        center_display_name = COLOR_NAME_KOR.get(center_colors.get(pos_face_label, '?'), '?') if pos_face_label else '?'
        print(f"Step {idx}: {mv} {arrow}")
        print(f"  [시점 재배치] {orient_instr} (센터: {center_display_name})")
        print(f"    -> {rot_instr}")
        print(f"  [동작] {KOREAN_FACE_FULL[base]} 을(를) {dir_text} 만큼 회전하세요.\n")

        if pos_face_label:
            current_view = pos_face_label

        apply_move_from_user_faces(faces, mv)
        display_net_state(faces, step=idx)

# ---------------- main session flow ----------------
def run_session(output_mode, coord_mode):
    faces = {}
    for f in FACE_ORDER:
        faces[f] = input_face(f)
    CENTER_COLORS = {f: faces[f][4] for f in FACE_ORDER}
    
    display_net_and_centers(faces)
    try:
        cube54 = build_kociemba_string(faces)
    except Exception as e:
        print("큐브 문자열 생성 오류:", e)
        return
    
    try:
        solution = safe_solve_with_kociemba(cube54)
    except Exception as e:
        print("솔버 오류:", e)
        return

    try:
        if output_mode == '1':
            print_solution_simple(solution, faces, coord_mode, CENTER_COLORS)
        else:
            print_solution_general(solution, faces, coord_mode, CENTER_COLORS)
    except Exception as e:
        print("출력 모드 처리 중 오류:", e)
        return
    
    input("모든 스텝 출력 완료. 계속하려면 Enter하세요.")

def main():
    while True:
        print_main_menu()
        choice = input_menu_choice("선택: ", ['1','2','3'])
        if choice == '1':
            print("\n[출력 버전 선택]")
            print("1) 심플 (간단 표기)")
            print("2) 일반 (상세 안내)")
            out_mode = input_menu_choice("선택 (1/2): ", ['1', '2'])

            print("\n[시점 방식 선택]")
            print("1) 고정시점 (흰색 정면, 빨강 윗면 기준)")
            print("2) 상대시점 (현재 보는 면 기준)")
            c_mode = input_menu_choice("선택 (1/2): ", ['1', '2'])

            run_session(out_mode, c_mode)
        elif choice == '2':
            show_explanation()
            input("설명 끝 — Enter 누르면 메뉴로 돌아갑니다.")
        elif choice == '3':
            print("프로그램을 종료합니다.")
            sys.exit(0)

if __name__ == '__main__':
    main()
