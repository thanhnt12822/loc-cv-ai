import hashlib
import hmac
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime

DB_PATH = "users.db"
SO_LAN_SAI_TOI_DA = 5
THOI_GIAN_KHOA = 300   # giây (5 phút)
SO_VONG_BAM = 600_000


def _ket_noi():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def _thuc_thi(sql, tham_so=()):
    with closing(_ket_noi()) as db, db:  # "db" thứ hai giúp tự lưu (commit)
        db.execute(sql, tham_so)


def _lay_mot(sql, tham_so=()):
    with closing(_ket_noi()) as db:
        return db.execute(sql, tham_so).fetchone()


def _lay_tat_ca(sql, tham_so=()):
    with closing(_ket_noi()) as db:
        return db.execute(sql, tham_so).fetchall()


def khoi_tao_db():
    _thuc_thi(
        """CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            ho_ten TEXT NOT NULL,
            salt BLOB NOT NULL,
            mat_khau_hash BLOB NOT NULL,
            vai_tro TEXT NOT NULL DEFAULT 'nguoi_dung',
            ngay_tao TEXT NOT NULL,
            so_lan_sai INTEGER NOT NULL DEFAULT 0,
            khoa_den REAL NOT NULL DEFAULT 0
        )"""
    )


def _bam(mat_khau, salt):
    return hashlib.pbkdf2_hmac("sha256", mat_khau.encode("utf-8"), salt, SO_VONG_BAM)


def kiem_tra_dinh_dang(username, mat_khau):
    if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
        return "Tên đăng nhập gồm 3-30 ký tự: chữ thường không dấu, số hoặc dấu gạch dưới."
    if len(mat_khau) < 8:
        return "Mật khẩu cần từ 8 ký tự trở lên."
    if len(mat_khau) > 128:
        return "Mật khẩu quá dài (tối đa 128 ký tự)."
    return None


def dang_ky(username, ho_ten, mat_khau):
    username = username.strip().lower()
    ho_ten = ho_ten.strip()
    if not ho_ten:
        return False, "Vui lòng nhập họ tên."
    loi = kiem_tra_dinh_dang(username, mat_khau)
    if loi:
        return False, loi

    la_nguoi_dau_tien = _lay_mot("SELECT COUNT(*) AS n FROM users")["n"] == 0
    salt = os.urandom(16)
    try:
        _thuc_thi(
            "INSERT INTO users (username, ho_ten, salt, mat_khau_hash, vai_tro, ngay_tao) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                username, ho_ten, salt, _bam(mat_khau, salt),
                "quan_tri" if la_nguoi_dau_tien else "nguoi_dung",
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
    except sqlite3.IntegrityError:
        return False, "Tên đăng nhập đã tồn tại."
    return True, "Đăng ký thành công. Hãy sang tab Đăng nhập."


def dang_nhap(username, mat_khau):
    """Trả về (thành công, thông báo, thông tin người dùng)."""
    username = username.strip().lower()
    loi_chung = "Sai tên đăng nhập hoặc mật khẩu."
    row = _lay_mot("SELECT * FROM users WHERE username = ?", (username,))
    if row is None:
        _bam(mat_khau, b"0" * 16)  # tốn thời gian như khi tài khoản có thật
        return False, loi_chung, None

    bay_gio = time.time()
    if row["khoa_den"] > bay_gio:
        phut = int(row["khoa_den"] - bay_gio) // 60 + 1
        return False, f"Tài khoản đang bị khóa tạm thời. Thử lại sau khoảng {phut} phút.", None

    if hmac.compare_digest(_bam(mat_khau, row["salt"]), row["mat_khau_hash"]):
        _thuc_thi("UPDATE users SET so_lan_sai = 0, khoa_den = 0 WHERE username = ?", (username,))
        return True, "", {
            "username": row["username"],
            "ho_ten": row["ho_ten"],
            "vai_tro": row["vai_tro"],
        }

    so_lan = row["so_lan_sai"] + 1
    if so_lan >= SO_LAN_SAI_TOI_DA:
        _thuc_thi(
            "UPDATE users SET so_lan_sai = 0, khoa_den = ? WHERE username = ?",
            (bay_gio + THOI_GIAN_KHOA, username),
        )
        return False, "Sai quá nhiều lần. Tài khoản bị khóa 5 phút.", None
    _thuc_thi("UPDATE users SET so_lan_sai = ? WHERE username = ?", (so_lan, username))
    return False, loi_chung, None


def danh_sach_nguoi_dung():
    cac_dong = _lay_tat_ca("SELECT username, ho_ten, vai_tro, ngay_tao FROM users ORDER BY ngay_tao")
    return [dict(d) for d in cac_dong]


def dat_lai_mat_khau(username, mat_khau_moi):
    loi = kiem_tra_dinh_dang(username, mat_khau_moi)
    if loi:
        return False, loi
    salt = os.urandom(16)
    _thuc_thi(
        "UPDATE users SET salt = ?, mat_khau_hash = ?, so_lan_sai = 0, khoa_den = 0 WHERE username = ?",
        (salt, _bam(mat_khau_moi, salt), username),
    )
    return True, f"Đã đặt lại mật khẩu cho {username}."