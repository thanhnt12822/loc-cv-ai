import logging

logging.getLogger("pdfminer").setLevel(logging.ERROR)
import re
import pdfplumber
import os
from datetime import date
import unicodedata
import hashlib
from datetime import datetime
from pathlib import Path

LIGATURE = {
    0xFB00: "ff", 0xFB01: "fi", 0xFB02: "fl", 0xFB03: "ffi", 0xFB04: "ffl",
}
KY_TU_LOI = r"\x00\ufffd\ue000-\uf8ff"
MAU_TOKEN_LOI = re.compile(rf"[\w{KY_TU_LOI}]*[{KY_TU_LOI}][\w{KY_TU_LOI}]*")
TU_CO_LIGATURE = {
    "firewall", "wifi", "file", "files", "office", "profile", "filter", "find",
    "first", "final", "fiber", "fibre", "fix", "fixed", "fine", "fill",
    "workflow", "flow", "flexible", "flash", "flat", "effective", "efficient",
    "offline", "offer", "official", "different", "difficult", "traffic",
    "staff", "effort", "affect", "reflect", "conflict",
}


def _sua_token_loi(m):
    token = m.group(0)
    chu_that = re.sub(f"[{KY_TU_LOI}]", "", token)
    if not any(c.isalpha() for c in chu_that):
        return ""  # ký tự lỗi đứng riêng (icon) -> bỏ
    for cum in ("fi", "fl", "ff", "ffi", "ffl"):
        thu = re.sub(f"[{KY_TU_LOI}]", cum, token)
        if thu.lower() in TU_CO_LIGATURE:
            return thu
    return re.sub(f"[{KY_TU_LOI}]", "fi", token)  # không có trong từ điển: đoán là "fi"


def sua_chu_loi(van_ban):
    van_ban = van_ban.translate(LIGATURE)
    return MAU_TOKEN_LOI.sub(_sua_token_loi, van_ban)

def _tim_diem_cat(trang):
    """Nếu CV có 2 cột, trả về vị trí ngang để cắt đôi trang; không có thì trả về None."""
    tu = trang.extract_words()
    if len(tu) < 30:
        return None
    rong = int(trang.width)
    co_chu = [False] * (rong + 2)
    for t in tu:
        for x in range(max(0, int(t["x0"])), min(rong, int(t["x1"])) + 1):
            co_chu[x] = True

    tot_nhat = None  # (độ rộng khoảng trống, vị trí giữa)
    x = int(rong * 0.15)
    gioi_han = int(rong * 0.75)
    while x < gioi_han:
        if co_chu[x]:
            x += 1
            continue
        bat_dau = x
        while x < gioi_han and not co_chu[x]:
            x += 1
        do_rong = x - bat_dau
        if do_rong >= 12 and (tot_nhat is None or do_rong > tot_nhat[0]):
            tot_nhat = (do_rong, (bat_dau + x) // 2)
    return tot_nhat[1] if tot_nhat else None


def doc_cv(nguon):
    """Đọc chữ từ PDF. CV 2 cột được đọc riêng từng cột để chữ không bị trộn."""
    cac_phan = []
    with pdfplumber.open(nguon) as pdf:
        for trang in pdf.pages:
            x0, top, x1, bottom = trang.bbox
            diem_cat = _tim_diem_cat(trang)
            if diem_cat is None:
                cac_phan.append(trang.extract_text() or "")
            else:
                trai = trang.crop((x0, top, diem_cat, bottom))
                phai = trang.crop((diem_cat, top, x1, bottom))
                cac_phan.append(trai.extract_text() or "")
                cac_phan.append(phai.extract_text() or "")
    noi_dung = "\n".join(p for p in cac_phan if p.strip())
    noi_dung = sua_chu_loi(noi_dung)
    return unicodedata.normalize("NFC", noi_dung)


def tim_email(van_ban):
    """Tìm email đầu tiên trong văn bản."""
    ket_qua = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", van_ban)
    return ket_qua.group(0) if ket_qua else None


def tim_so_dien_thoai(van_ban):
    """Tìm số điện thoại Việt Nam (0xxxxxxxxx hoặc +84xxxxxxxxx)."""
    ket_qua = re.search(r"(?:\+84|0)(?:[\s.-]?\d){9}", van_ban)
    return ket_qua.group(0) if ket_qua else None


def kiem_tra_ky_nang(van_ban, danh_sach_tu_khoa):
    """Trả về 2 danh sách: kỹ năng có trong CV và kỹ năng còn thiếu."""
    van_ban_thuong = van_ban.lower()
    co = [k for k in danh_sach_tu_khoa if k.lower() in van_ban_thuong]
    thieu = [k for k in danh_sach_tu_khoa if k.lower() not in van_ban_thuong]
    return co, thieu

def tim_ngay_sinh(van_ban):
    """Tìm ngày sinh theo nhiều kiểu ghi. Trả về date hoặc None."""
    nam_toi_da = date.today().year - 14

    def tao_ngay(ngay, thang, nam):
        try:
            if 1940 <= nam <= nam_toi_da:
                return date(nam, thang, ngay)
        except ValueError:
            pass
        return None

    # Kiểu 1: có nhãn "Ngày sinh", "DOB"... rồi đến dd/mm/yyyy
    mau1 = r"(?:ngày sinh|date of birth|dob|birthday|sinh ngày|born)\D{0,20}?(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})"
    m = re.search(mau1, van_ban, re.IGNORECASE)
    if m:
        kq = tao_ngay(*map(int, m.groups()))
        if kq:
            return kq

    # Kiểu 2: "15 tháng 3, 1998" hoặc "15 tháng 03 năm 1998"
    mau2 = r"(\d{1,2})\s*tháng\s*(\d{1,2})[\s,]*(?:năm)?\s*(\d{4})"
    m = re.search(mau2, van_ban, re.IGNORECASE)
    if m:
        kq = tao_ngay(*map(int, m.groups()))
        if kq:
            return kq

    # Kiểu 3: không có nhãn, tìm bất kỳ ngày đầy đủ dd/mm/yyyy hợp lý
    for m in re.finditer(r"(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})", van_ban):
        kq = tao_ngay(*map(int, m.groups()))
        if kq:
            return kq

    # Kiểu 4: chỉ có năm sinh (lấy ngày 1/1 để ước tính tuổi)
    m = re.search(r"(?:năm sinh|sinh năm)\D{0,10}?(\d{4})", van_ban, re.IGNORECASE)
    if m:
        return tao_ngay(1, 1, int(m.group(1)))

    return None


def tinh_tuoi(ngay_sinh):
    hom_nay = date.today()
    tuoi = hom_nay.year - ngay_sinh.year
    if (hom_nay.month, hom_nay.day) < (ngay_sinh.month, ngay_sinh.day):
        tuoi -= 1
    return tuoi


def tim_so_nam_kinh_nghiem(van_ban):
    """Ước lượng số năm kinh nghiệm."""
    # Cách 1: CV ghi thẳng "3 năm kinh nghiệm" / "3 years of experience"
    mau = r"(\d+(?:[.,]\d+)?)\+?\s*(?:năm|years?)\s*(?:kinh nghiệm|of experience|experience)"
    ket_qua = re.search(mau, van_ban, re.IGNORECASE)
    if ket_qua:
        return float(ket_qua.group(1).replace(",", "."))

    # Cách 2: cộng các khoảng "03/2019 - 06/2022" hoặc "03/2021 - nay"
    mau_khoang = r"(\d{1,2})/(\d{4})\s*[-–]\s*(?:(\d{1,2})/(\d{4})|nay|hiện tại|present|now)"
    hom_nay = date.today()
    tong_thang = 0
    for m in re.finditer(mau_khoang, van_ban, re.IGNORECASE):
        thang1, nam1 = int(m.group(1)), int(m.group(2))
        if m.group(3):
            thang2, nam2 = int(m.group(3)), int(m.group(4))
        else:
            thang2, nam2 = hom_nay.month, hom_nay.year
        so_thang = (nam2 - nam1) * 12 + (thang2 - thang1)
        if so_thang > 0:
            tong_thang += so_thang
    return round(tong_thang / 12, 1)


TU_KHOA_IT = [
    "developer", "lập trình", "software engineer", "kỹ sư phần mềm",
    "backend", "frontend", "fullstack", "tester", "devops",
    "data analyst", "it support", "python", "java", "sql",
]


def tim_tu_khoa_it(van_ban):
    """Trả về các từ khóa ngành IT xuất hiện trong CV."""
    van_ban_thuong = van_ban.lower()
    return [t for t in TU_KHOA_IT if t in van_ban_thuong]
CHUC_DANH_IT = [
    "it support", "it helpdesk", "helpdesk", "help desk",
    "technical support", "hỗ trợ kỹ thuật", "hỗ trợ it",
    "system admin", "sysadmin", "quản trị hệ thống",
    "network", "mạng máy tính",
    "developer", "lập trình viên", "software engineer",
    "tester", "devops", "data analyst",
]


def tim_chuc_danh_it(van_ban):
    """Trả về các chức danh/vị trí IT xuất hiện trong CV."""
    van_ban_thuong = van_ban.lower()
    return [c for c in CHUC_DANH_IT if c in van_ban_thuong]

YEU_CAU_KY_NANG = {
    "Hệ điều hành": ["windows", "linux", "macos", "windows server"],
    "Mạng": ["tcp/ip", "dns", "dhcp", "vpn", "wifi", "router", "firewall", "cisco"],
    "Phần cứng": ["hardware", "phần cứng", "sửa chữa máy tính", "máy in", "printer", "bảo trì"],
    "Hệ thống & tài khoản": ["active directory", "office 365", "microsoft 365", "azure ad", "group policy", "exchange"],
    "Hỗ trợ người dùng": ["ticket", "helpdesk", "help desk", "service desk", "teamviewer", "anydesk", "remote desktop", "itil"],
    "Ngoại ngữ": ["tiếng anh", "english", "toeic", "ielts"],
}

def kiem_tra_nhom_ky_nang(van_ban, yeu_cau):
    """Với mỗi nhóm kỹ năng, trả về các từ khóa tìm thấy trong CV."""
    ket_qua = {}
    for nhom, tu_khoa in yeu_cau.items():
        co, _ = kiem_tra_ky_nang(van_ban, tu_khoa)
        ket_qua[nhom] = co
    return ket_qua
def tim_chuc_danh(van_ban, danh_sach):
    """Trả về các chức danh trong danh_sach xuất hiện trong CV."""
    van_ban_thuong = van_ban.lower()
    return [c for c in danh_sach if c in van_ban_thuong]


CHUC_DANH_KE_TOAN = [
    "kế toán viên", "nhân viên kế toán", "chuyên viên kế toán",
    "kế toán tổng hợp", "kế toán trưởng", "kế toán thuế", "kế toán công nợ",
    "kế toán kho", "kế toán bán hàng", "kế toán nội bộ", "kế toán thanh toán",
    "kế toán giá thành", "kế toán tiền lương", "kiểm toán viên",
    "accountant", "bookkeeper", "auditor",
]

YEU_CAU_KE_TOAN = {
    "Phần mềm kế toán": ["misa", "fast accounting", "bravo", "ecount", "acman",
                         "quickbooks", "sap erp", "sap b1", "sap business one"],
    "Excel": ["excel", "vlookup", "pivot"],
    "Nghiệp vụ kế toán": ["hạch toán", "sổ sách", "chứng từ", "bút toán", "công nợ",
                          "báo cáo tài chính", "bảng cân đối", "tài sản cố định",
                          "giá thành", "kiểm kê"],
    "Thuế & hóa đơn": ["kê khai thuế", "quyết toán thuế", "thuế gtgt", "thuế tndn",
                       "thuế tncn", "hóa đơn điện tử", "htkk", "báo cáo thuế"],
    "Tiền, lương & bảo hiểm": ["thu chi", "sổ quỹ", "quỹ tiền mặt", "ngân hàng",
                               "bảng lương", "tiền lương", "bhxh", "bảo hiểm xã hội"],
    "Chứng chỉ & ngoại ngữ": ["chứng chỉ kế toán", "acca", "cpa", "cima", "vacpa",
                              "tiếng anh", "english", "toeic", "ielts"],
}
CHUC_DANH_NHAN_SU = [
    "chuyên viên nhân sự", "nhân viên nhân sự", "nhân sự tổng hợp",
    "hành chính nhân sự", "trưởng phòng nhân sự", "chuyên viên tuyển dụng",
    "nhân viên tuyển dụng", "chuyên viên c&b", "chuyên viên đào tạo",
    "recruiter", "talent acquisition", "recruitment", "human resources",
    "hr executive", "hr specialist", "hr generalist", "hr assistant",
    "hr admin", "hr manager", "hrbp", "hr business partner",
]

YEU_CAU_NHAN_SU = {
    "Tuyển dụng": ["tuyển dụng", "sàng lọc cv", "phỏng vấn", "đăng tin tuyển dụng",
                   "headhunt", "talent acquisition", "topcv", "vietnamworks",
                   "careerbuilder", "linkedin", "job description"],
    "C&B: lương, bảo hiểm": ["c&b", "tiền lương", "bảng lương", "chấm công",
                             "bhxh", "bảo hiểm xã hội", "chế độ phúc lợi", "thuế tncn"],
    "Hồ sơ & luật lao động": ["bộ luật lao động", "luật lao động", "hợp đồng lao động",
                              "hồ sơ nhân sự", "nội quy", "quy chế", "kỷ luật lao động"],
    "Đào tạo & phát triển": ["đào tạo", "onboarding", "hội nhập nhân viên",
                             "đánh giá nhân viên", "kpi", "đánh giá hiệu suất",
                             "văn hóa doanh nghiệp", "gắn kết nhân viên"],
    "Phần mềm & văn phòng": ["excel", "amis", "office", "base hrm", "hrm",
                             "microsoft office", "google sheet"],
    "Giao tiếp & ngoại ngữ": ["giao tiếp", "đàm phán", "tiếng anh", "english",
                              "toeic", "ielts"],
}
# Danh sách các vị trí tuyển dụng. Muốn thêm vị trí mới: copy một khối rồi sửa.
VI_TRI = {
    "IT Support": {
        "ma": "it_support",
        "chuc_danh": CHUC_DANH_IT,
        "ky_nang": YEU_CAU_KY_NANG,
        "kn_min": 2.0,      # số năm kinh nghiệm tối thiểu mặc định
        "nhom_min": 3,      # số nhóm kỹ năng tối thiểu mặc định
    },
    "Kế toán": {
        "ma": "ke_toan",
        "chuc_danh": CHUC_DANH_KE_TOAN,
        "ky_nang": YEU_CAU_KE_TOAN,
        "kn_min": 2.0,
        "nhom_min": 3,
    },
        "Nhân sự": {
        "ma": "nhan_su",
        "chuc_danh": CHUC_DANH_NHAN_SU,
        "ky_nang": YEU_CAU_NHAN_SU,
        "kn_min": 2.0,
        "nhom_min": 3,
    },
}