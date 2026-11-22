import io
import unicodedata

import docx
import pandas as pd
import streamlit as st
import hashlib
from datetime import date, datetime
from pathlib import Path
import html
import re

from ai_ollama import danh_sach_model, lam_nong_model, nhan_xet_cv, OLLAMA_URL, MODEL_MAC_DINH

from auth import (
    dang_ky,
    dang_nhap,
    danh_sach_nguoi_dung,
    dat_lai_mat_khau,
    khoi_tao_db,
)
from cv_reader import (
    VI_TRI,
    doc_cv,
    kiem_tra_nhom_ky_nang,
    tim_chuc_danh,
    tim_email,
    tim_ngay_sinh,
    tim_so_dien_thoai,
    tim_so_nam_kinh_nghiem,
    tinh_tuoi,
)

st.set_page_config(page_title="Kiểm tra CV", layout="wide")
st.markdown(
    """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.banner {
    background: linear-gradient(135deg, #2E7D32, #66BB6A);
    color: white; padding: 1.5rem 2rem; border-radius: 16px; margin-bottom: 1.5rem;
}
.banner h1 {color: white; margin: 0; font-size: 2rem;}
.banner p {margin: .3rem 0 0; opacity: .9;}
div[data-testid="stMetric"] {
    background: white; border: 1px solid #C8E6C9; border-left: 6px solid #2E7D32;
    padding: 1rem; border-radius: 12px; box-shadow: 0 2px 6px rgba(46,125,50,.08);
}
.stButton > button, .stDownloadButton > button {
    background: #2E7D32; color: white; border: none; border-radius: 8px;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: #1B5E20; color: white;
}
section[data-testid="stSidebar"] {border-right: 1px solid #C8E6C9;}
.kn-card {
    background: white; border: 1px solid #C8E6C9; border-left: 6px solid #2E7D32;
    border-radius: 12px; padding: 1rem 1.2rem; margin-bottom: .8rem;
    box-shadow: 0 2px 6px rgba(46,125,50,.08);
}
.kn-time {
    display: inline-block; background: #E8F5E9; color: #1B5E20;
    padding: .15rem .7rem; border-radius: 999px; font-size: .85rem;
    font-weight: 600; margin-bottom: .4rem;
}
.kn-title {font-weight: 700; font-size: 1.05rem; color: #1B3A1F;}
.kn-card ul {margin: .4rem 0 0 1.1rem; padding: 0; color: #1B3A1F;}
</style>
""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="banner"><h1>Kiểm tra CV ứng viên công ty CHÁNH THU</h1>'
    "<p>Tải CV lên, hệ thống tự động sàng lọc theo tiêu chí.</p></div>",
    unsafe_allow_html=True,
)



# ---- Tiêu chí (thanh bên trái) ----
khoi_tao_db()

try:
    MA_MOI = st.secrets["MA_MOI"]
except Exception:
    MA_MOI = ""  # để trống = ai cũng đăng ký được (chỉ nên dùng khi chạy thử trên máy bạn)

try:
    URL_OLLAMA = st.secrets["OLLAMA_URL"]   # nếu Ollama chạy ở máy khác
except Exception:
    URL_OLLAMA = OLLAMA_URL


@st.cache_data(ttl=30)
def lay_model(url):
    try:
        return danh_sach_model(url)
    except Exception:
        return []

#nạp sẵn model vào bộ nhớ tạm
@st.cache_resource
def nap_san(model, url):
    """Nạp sẵn model vào bộ nhớ (chạy nền), chỉ làm một lần cho mỗi model."""
    lam_nong_model(model, url)
    return True

def man_hinh_dang_nhap():
    st.subheader("Đăng nhập hệ thống")
    tab_dn, tab_dk = st.tabs(["Đăng nhập", "Đăng ký"])

    with tab_dn:
        with st.form("form_dang_nhap"):
            ten = st.text_input("Tên đăng nhập")
            mk = st.text_input("Mật khẩu", type="password")
            gui = st.form_submit_button("Đăng nhập")
        if gui:
            ok, thong_bao, nguoi_dung = dang_nhap(ten, mk)
            if ok:
                st.session_state["user"] = nguoi_dung
                st.rerun()
            else:
                st.error(thong_bao)

    with tab_dk:
        with st.form("form_dang_ky"):
            ho_ten = st.text_input("Họ và tên")
            ten_moi = st.text_input("Tên đăng nhập (chữ thường không dấu, số, gạch dưới)")
            mk1 = st.text_input("Mật khẩu (từ 8 ký tự)", type="password")
            mk2 = st.text_input("Nhập lại mật khẩu", type="password")
            ma = st.text_input("Mã mời (do quản trị viên cấp)", type="password") if MA_MOI else ""
            gui2 = st.form_submit_button("Tạo tài khoản")
        if gui2:
            if MA_MOI and ma != MA_MOI:
                st.error("Mã mời không đúng.")
            elif mk1 != mk2:
                st.error("Hai mật khẩu không khớp.")
            else:
                ok, thong_bao = dang_ky(ten_moi, ho_ten, mk1)
                if ok:
                    st.success(thong_bao)
                else:
                    st.error(thong_bao)


if "user" not in st.session_state:
    man_hinh_dang_nhap()
    st.stop()  # chưa đăng nhập thì dừng ở đây, không hiện phần bên dưới

user = st.session_state["user"]

st.markdown("#### 1. Chọn vị trí tuyển dụng")
vi_tri = st.selectbox(
    "Vị trí cần kiểm tra",
    list(VI_TRI.keys()),
    label_visibility="collapsed",
)
cau_hinh = VI_TRI[vi_tri]
ma_vt = cau_hinh["ma"]

with st.sidebar:
    st.write(f"Xin chào, **{user['ho_ten']}**")
    if st.button("Đăng xuất"):
        st.session_state.pop("user", None)
        st.rerun()
    st.divider()
    # giữ nguyên các ô nhập tiêu chí bên dưới
    st.header("Tiêu chí tuyển dụng")
    st.caption(f"Đang kiểm tra theo vị trí: **{vi_tri}**")
    tuoi_min = st.number_input("Tuổi tối thiểu", 15, 60, 18)
    kn_min = st.number_input(
        "Số năm kinh nghiệm tối thiểu", 0.0, 30.0, cau_hinh["kn_min"],
        step=0.5, key=f"kn_{ma_vt}",
    )
    nhom_min = st.number_input(
        "Số nhóm kỹ năng tối thiểu", 0, len(cau_hinh["ky_nang"]),
        cau_hinh["nhom_min"], key=f"nhom_{ma_vt}",
    )
    chi_tinh_vt = st.checkbox("Chỉ tính kinh nghiệm đúng vị trí", value=True)
    st.divider()
    st.header("AI nhận xét (Ollama)")
    cac_model = lay_model(URL_OLLAMA)
    if cac_model:
        mac_dinh = cac_model.index(MODEL_MAC_DINH) if MODEL_MAC_DINH in cac_model else 0
        model_ai = st.selectbox("Model AI", cac_model, index=mac_dinh)
        nap_san(model_ai, URL_OLLAMA)
    else:
        model_ai = None
        st.warning("Chưa kết nối được Ollama hoặc chưa tải model nào.")

    with st.expander("Xem yêu cầu của vị trí"):
        st.write("**Chức danh được chấp nhận:**", ", ".join(cau_hinh["chuc_danh"]))
        for nhom, tu_khoa in cau_hinh["ky_nang"].items():
            st.write(f"**{nhom}:**", ", ".join(tu_khoa))
       

            

@st.cache_data(show_spinner=False, ttl=1800, max_entries=30)
def doc_noi_dung(ten_file, du_lieu):
    """Đọc chữ từ PDF/Word. Kết quả được nhớ tạm 30 phút để không phải đọc lại mỗi lần bấm nút."""
    nguon = io.BytesIO(du_lieu)
    ten = ten_file.lower()
    if ten.endswith(".pdf"):
        return doc_cv(nguon)
    if ten.endswith(".docx"):
        tai_lieu = docx.Document(nguon)
        cac_dong = [p.text for p in tai_lieu.paragraphs]
        for bang in tai_lieu.tables:  # nhiều CV Word đặt nội dung trong bảng
            for hang in bang.rows:
                for o in hang.cells:
                    cac_dong.append(o.text)
        return unicodedata.normalize("NFC", "\n".join(cac_dong))
    return ""


def phan_tich(van_ban, cau_hinh):
    ngay_sinh = tim_ngay_sinh(van_ban)
    tuoi = tinh_tuoi(ngay_sinh) if ngay_sinh else None
    cac_muc = tach_muc_kinh_nghiem(van_ban)
    so_nam = tinh_so_nam_kinh_nghiem(cac_muc)
    so_nam_vt = tinh_so_nam_kinh_nghiem(cac_muc, cau_hinh["chuc_danh"])
    if not cac_muc:  # không tách được mục kinh nghiệm -> ước lượng kiểu cũ
        so_nam = tim_so_nam_kinh_nghiem(van_ban)
        so_nam_vt = None
    so_nam_xet = so_nam_vt if (chi_tinh_vt and so_nam_vt is not None) else so_nam

    chuc_danh = tim_chuc_danh(van_ban, cau_hinh["chuc_danh"])
    nhom = kiem_tra_nhom_ky_nang(van_ban, cau_hinh["ky_nang"])
    so_nhom = sum(1 for co in nhom.values() if co)

    ly_do = []
    if tuoi is None or tuoi < tuoi_min:
        ly_do.append("tuổi/ngày sinh")
    if so_nam_xet < kn_min:
        ly_do.append("số năm kinh nghiệm")
    if not chuc_danh:
        ly_do.append("chức danh phù hợp")
    if so_nhom < nhom_min:
        ly_do.append("kỹ năng")

    return {
        "ngay_sinh": ngay_sinh, "tuoi": tuoi, "so_nam": so_nam,
        "so_nam_vt": so_nam_vt,
        "chuc_danh": chuc_danh, "nhom": nhom, "so_nhom": so_nhom,
        "ly_do": ly_do,
        "cac_muc": cac_muc,
    }

TIEU_DE_KINH_NGHIEM = [
    "kinh nghiệm làm việc", "kinh nghiệm", "quá trình làm việc",
    "quá trình công tác", "lịch sử làm việc", "work experience",
    "experience", "professional experience", "employment history", "work history",
]
TIEU_DE_KHAC = [
    "học vấn", "trình độ học vấn", "education", "kỹ năng", "kỹ năng chuyên môn",
    "skills", "dự án", "projects", "chứng chỉ", "certifications", "giải thưởng",
    "awards", "sở thích", "hobbies", "người tham chiếu", "references",
    "thông tin cá nhân", "personal information", "mục tiêu nghề nghiệp",
    "career objective", "objective", "hoạt động", "activities", "ngoại ngữ", "languages",
]
MAU_THOI_GIAN = re.compile(
    r"((?:\d{1,2}\s*/\s*)?\d{4})\s*[-–—]\s*"
    r"((?:\d{1,2}\s*/\s*)?\d{4}|nay|hiện tại|present|now|current)",
    re.IGNORECASE,
)


def chuan_hoa_dong(dong):
    return re.sub(r"[^\w\s]", "", dong.lower()).strip()


def an_toan(chuoi):
    return html.escape(chuoi).replace("$", "&#36;")


def tach_muc_kinh_nghiem(van_ban):
    """Lấy phần kinh nghiệm làm việc, chia thành từng công việc."""
    cac_dong = [d.strip() for d in van_ban.splitlines()]
    bat_dau = None
    for i, d in enumerate(cac_dong):
        if chuan_hoa_dong(d) in TIEU_DE_KINH_NGHIEM:
            bat_dau = i + 1
            break
    if bat_dau is None:
        return []

    noi_dung = []
    for d in cac_dong[bat_dau:]:
        if chuan_hoa_dong(d) in TIEU_DE_KHAC:
            break
        if d:
            noi_dung.append(d)

    cac_muc, hien_tai = [], None
    for dong in noi_dung:
        m = MAU_THOI_GIAN.search(dong)
        if m:
            hien_tai = {"thoi_gian": m.group(0), "dong": []}
            cac_muc.append(hien_tai)
            con_lai = (dong[:m.start()] + " " + dong[m.end():]).strip(" -–—:|,()")
            if con_lai:
                hien_tai["dong"].append(con_lai)
        else:
            if hien_tai is None:
                hien_tai = {"thoi_gian": "", "dong": []}
                cac_muc.append(hien_tai)
            hien_tai["dong"].append(dong)
    return cac_muc


def hien_thi_kinh_nghiem(cac_muc):
    for m in cac_muc:
        cac_dong = [d.lstrip("-•*·▪▫●○ ").strip() for d in m["dong"]]
        cac_dong = [d for d in cac_dong if d]
        tieu_de = an_toan(cac_dong[0]) if cac_dong else "Không rõ vị trí"
        li = "".join(f"<li>{an_toan(d)}</li>" for d in cac_dong[1:])
        thoi_gian = (f'<div class="kn-time">{an_toan(m["thoi_gian"])}</div>'
                     if m["thoi_gian"] else "")
        danh_sach = f"<ul>{li}</ul>" if li else ""
        st.markdown(
            f'<div class="kn-card">{thoi_gian}'
            f'<div class="kn-title">{tieu_de}</div>{danh_sach}</div>',
            unsafe_allow_html=True,
        )

def sach(chu):
    return str(chu).replace("$", r"\$")


def hien_thi_nhan_xet(nx):
    if "loi" in nx:
        st.error(nx["loi"])
        return
    if "van_ban_tho" in nx:
        st.markdown(sach(nx["van_ban_tho"]))
        return
    muc = nx.get("muc_phu_hop", "")
    hop = {"Rất phù hợp": st.success, "Phù hợp": st.success,
           "Cân nhắc": st.warning, "Chưa phù hợp": st.error}
    hop.get(muc, st.info)(f"**Mức phù hợp (AI gợi ý): {muc}**")
    st.markdown(sach(nx.get("tom_tat", "")))
    for tieu_de, khoa in [
        ("Điểm mạnh", "diem_manh"),
        ("Cần làm rõ", "can_lam_ro"),
        ("Câu hỏi phỏng vấn gợi ý", "cau_hoi_phong_van"),
        ("Cảnh báo", "canh_bao"),
    ]:
        ds = nx.get(khoa) or []
        if isinstance(ds, str):
            ds = [ds]
        if ds:
            st.markdown(f"**{tieu_de}**")
            for d in ds:
                st.markdown("- " + sach(d))

st.markdown("#### 2. Tải CV lên")

files = st.file_uploader(
    "Kéo thả CV vào đây (PDF hoặc Word, có thể chọn nhiều file)",
    type=["pdf", "docx"],
    accept_multiple_files=True,
)

def doc_thang(chuoi, thang_mac_dinh):
    """'08/2019' -> (2019, 8); '2019' -> (2019, thang_mac_dinh)."""
    m = re.match(r"(?:(\d{1,2})\s*/\s*)?(\d{4})", chuoi.strip())
    if not m:
        return None
    thang = int(m.group(1)) if m.group(1) else thang_mac_dinh
    return int(m.group(2)), thang


def tinh_so_nam_kinh_nghiem(cac_muc, chuc_danh=None):
    """Cộng thời gian các công việc trong mục kinh nghiệm (gộp phần chồng nhau)."""
    hom_nay = date.today()
    thang_nay = hom_nay.year * 12 + hom_nay.month
    khoang = []
    for muc in cac_muc:
        if chuc_danh:
            chu = " ".join(muc["dong"]).lower()
            if not any(c in chu for c in chuc_danh):
                continue
        m = MAU_THOI_GIAN.search(muc["thoi_gian"])
        if not m:
            continue
        bd = doc_thang(m.group(1), 1)
        if bd is None:
            continue
        kt = doc_thang(m.group(2), 12)
        s = bd[0] * 12 + bd[1]
        e = kt[0] * 12 + kt[1] if kt else thang_nay  # "nay", "present" -> hôm nay
        e = min(e, thang_nay)
        if e > s:
            khoang.append((s, e))

    khoang.sort()
    tong, hien_tai = 0, None
    for s, e in khoang:
        if hien_tai is None:
            hien_tai = [s, e]
        elif s <= hien_tai[1]:
            hien_tai[1] = max(hien_tai[1], e)
        else:
            tong += hien_tai[1] - hien_tai[0]
            hien_tai = [s, e]
    if hien_tai:
        tong += hien_tai[1] - hien_tai[0]
    return round(tong / 12, 1)

if files:
    dong_tong_hop = []
    chi_tiet = {}

    for f in files:
        van_ban = doc_noi_dung(f.name, f.getvalue())
        if not van_ban.strip():
            dong_tong_hop.append({"File": f.name, "Kết luận": "Không đọc được chữ (có thể là ảnh scan)"})
            continue

        kq = phan_tich(van_ban, cau_hinh)
        chi_tiet[f.name] = (van_ban, kq)
        dong_tong_hop.append({
            "File": f.name,
            "Email": tim_email(van_ban),
            "SĐT": tim_so_dien_thoai(van_ban),
            "Tuổi": kq["tuoi"],
            "Năm KN": kq["so_nam"],
            "Năm KN vị trí": kq["so_nam_vt"],
            "Nhóm kỹ năng": f'{kq["so_nhom"]}/{len(cau_hinh["ky_nang"])}',
            "Kết luận": "PHÙ HỢP" if not kq["ly_do"] else "Cần xem lại: " + ", ".join(kq["ly_do"]),
        })

    bang = pd.DataFrame(dong_tong_hop)

    tong = len(dong_tong_hop)
    phu_hop = sum(1 for d in dong_tong_hop if d["Kết luận"] == "PHÙ HỢP")
    c1, c2, c3 = st.columns(3)
    c1.metric("Tổng số CV", tong)
    c2.metric("Phù hợp", phu_hop)
    c3.metric("Cần xem lại", tong - phu_hop)

    st.subheader(f"Tổng hợp: vị trí {vi_tri}")

    def to_mau(gia_tri):
        if gia_tri == "PHÙ HỢP":
            return "background-color: #C8E6C9; color: #1B5E20; font-weight: bold"
        return "background-color: #FFF3E0; color: #E65100"

    
    st.dataframe(
        bang.style
        .map(to_mau, subset=["Kết luận"])
        .format(na_rep="-")
        .format({"Tuổi": "{:.0f}", "Năm KN": "{:g}", "Năm KN vị trí": "{:g}"}, na_rep="Không rõ"),
        use_container_width=True,
    )

    #tải bảng kết quả ra exel
    bo_nho = io.BytesIO()
    bang_xuat = bang.copy()
    bang_xuat.insert(0, "Vị trí", vi_tri)
    bang_xuat.to_excel(bo_nho, index=False)
    st.download_button("Tải bảng kết quả (Excel)", bo_nho.getvalue(), f"ket_qua_cv_{ma_vt}.xlsx")

    st.subheader("Chi tiết từng CV")
    for ten, (van_ban, kq) in chi_tiet.items():
        with st.expander(ten):
            st.write("**Ngày sinh:**", kq["ngay_sinh"] or "không tìm thấy")
            st.write("**Chức danh phù hợp:**", kq["chuc_danh"] or "không thấy")

            for nhom, co in kq["nhom"].items():
                st.write(("✔ " if co else "✘ ") + nhom + ":", ", ".join(co) if co else "-")
            st.markdown("#### Nhận xét của AI")
            if not model_ai:
                st.info("Cần chạy Ollama và tải ít nhất một model để dùng nhận xét AI.")
            else:
                khoa = "nx_" + hashlib.md5((ma_vt + model_ai + van_ban).encode("utf-8")).hexdigest()[:12]
                if st.button("Nhờ AI nhận xét CV này", key=f"btn_{khoa}_{ten}"):
                    with st.spinner("AI đang đọc CV (lần đầu có thể mất vài chục giây)..."):
                        try:
                            st.session_state[khoa] = nhan_xet_cv(
                                van_ban, vi_tri, cau_hinh, kq, model_ai, URL_OLLAMA
                            )
                        except Exception as e:
                            st.session_state[khoa] = {
                                "loi": f"Không gọi được Ollama ({type(e).__name__}). "
                                       "Kiểm tra Ollama đang chạy, model đã tải, và máy đủ mạnh."
                            }
                if khoa in st.session_state:
                    hien_thi_nhan_xet(st.session_state[khoa])
            st.markdown("#### Kinh nghiệm làm việc")
            cac_muc = tach_muc_kinh_nghiem(van_ban)
            if cac_muc:
                hien_thi_kinh_nghiem(cac_muc)
            else:
                st.warning("Không tìm thấy mục kinh nghiệm làm việc trong CV này.")

            if st.checkbox("Xem toàn bộ nội dung chữ đọc được", key="all_" + ten):
                st.text_area("Nội dung chữ đọc được", van_ban, height=200, key="txt_" + ten)
st.divider()


if user["vai_tro"] == "quan_tri":
    st.divider()
    with st.expander("Quản trị: danh sách tài khoản"):
        ds = danh_sach_nguoi_dung()
        st.dataframe(pd.DataFrame(ds), use_container_width=True)
        with st.form("form_dat_lai"):
            ten_dl = st.selectbox("Tài khoản", [u["username"] for u in ds])
            mk_dl = st.text_input("Mật khẩu mới (từ 8 ký tự)", type="password")
            gui_dl = st.form_submit_button("Đặt lại mật khẩu")
            if gui_dl:
                ok, thong_bao = dat_lai_mat_khau(ten_dl, mk_dl)
                if ok:
                    st.success(thong_bao)
                else:
                    st.error(thong_bao)