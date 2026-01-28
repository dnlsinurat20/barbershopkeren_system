import streamlit as st
import pandas as pd
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import date, datetime, timedelta
import urllib.parse
import time
import io
import os 
from PIL import Image, ImageDraw, ImageFont
import base64
import requests
import json
import altair as alt

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="TRIPL3 Barbershop System", page_icon="💈", layout="wide")

# --- DATA PROFIL KAPSTER ---
INFO_KAPSTER = {
    "Dariuz Hia": {
        "deskripsi": "Senior Hairstylist. Spesialis Haircut Modern, Haircut Classic, & Koreanstyle",
        "img": "dariuz.jpeg" 
    },
    "David": {
        "deskripsi": "Senior Haircut. Spesialis Haircut Modern, Haircut Classic & Hairstyle.",
        "img": "david.jpeg"
    },
    "Herry": {
        "deskripsi": "Senior haircut. Spesialis Haircut modern, Haircut Classic & Hairstyle.",
        "img": "herry.jpeg"
    }
}

# --- SEMBUNYIKAN TULISAN LIMIT UPLOAD ---
st.markdown("""
<style>
    /* Menyembunyikan tulisan kecil "Limit 200MB per file" */
    [data-testid="stFileUploader"] section > div > small {
        display: none;
    }
</style>
""", unsafe_allow_html=True)

# --- IMPORT LIBRARY BARU (Untuk Drive) ---
# Jangan hapus import lama Anda (oauth2client), biarkan saja.
# Tambahkan import baru ini di bawahnya:
from google.oauth2 import service_account

# --- KONFIGURASI DRIVE ---
# Masukkan ID Folder Drive yang sudah Anda buat tadi
FOLDER_ID_DRIVE = "1nGF6UB02BwaueuposGPQMe8DiTLi_B1w" 

# --- KONFIGURASI WEB APP ---
# 👇 PASTE URL PANJANG DARI APPS SCRIPT DI SINI (JANGAN SAMPAI ADA SPASI)
SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxiJBqeKEkZy3Ap5M0Xgibfqfg2ZcNTkq6BNresaD91EGJ3WM6HeIsoddo28XXvq7tTdg/exec" 

# --- FUNGSI UPLOAD VERSI ANTI-ERROR ---
def upload_ke_drive(file_buffer, nama_file_simpan):
    try:
        # 1. Konversi Gambar ke Base64
        string_gambar = base64.b64encode(file_buffer.getvalue()).decode('utf-8')
        
        # 2. Siapkan Paket Data
        payload = {
            "filename": nama_file_simpan,
            "image": string_gambar
        }
        
        # 3. Kirim ke Google Apps Script
        headers = {'Content-Type': 'application/json'}
        response = requests.post(SCRIPT_URL, data=json.dumps(payload), headers=headers)
        
        # 4. Cek Balasan
        if response.status_code == 200:
            hasil = response.json() # <--- Variabel 'hasil' baru dibuat di sini
            
            if hasil.get("result") == "success":
                return hasil.get("link") # Langsung return Link jika sukses
            else:
                st.error(f"Gagal dari Server: {hasil.get('message')}")
                return None
        else:
            st.error(f"Error HTTP: {response.status_code}")
            return None

    except Exception as e:
        st.error(f"Error Koneksi Python: {e}")
        return None 
        # Di sini kita return None, BUKAN return hasil
        # Jadi kalau error, tidak akan memaksa memanggil variabel yang tidak ada.
    
# --- FUNGSI FORMAT ANGKA (RUPIAH) ---
def format_angka(nilai):
    return "{:,.0f}".format(nilai).replace(',', '.')
    
# --- FUNGSI FORMAT TANGGAL INDONESIA ---
def tanggal_indo(tgl_str):
    try:
        # Daftar Nama Bulan
        bulan_indo = {
            1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
            5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
            9: "September", 10: "Oktober", 11: "November", 12: "Desember"
        }
        
        # Jika inputnya sudah datetime object (dari st.date_input)
        if isinstance(tgl_str, (date, datetime)):
            tgl_obj = tgl_str
        else:
            # Jika inputnya string dari database 'YYYY-MM-DD'
            tgl_obj = datetime.strptime(str(tgl_str), "%Y-%m-%d")
            
        return f"{tgl_obj.day} {bulan_indo[tgl_obj.month]} {tgl_obj.year}"
    except:
        return tgl_str # Jika error, kembalikan apa adanya

# --- FUNGSI GENERATE NOMOR NOTA (YYMMxxx) ---
def get_next_invoice_number():
    try:
        # 1. Tentukan Prefix (2601 untuk Jan 2026)
        now = datetime.utcnow() + timedelta(hours=7)
        prefix = now.strftime("%y%m") # Format YYMM
        current_month_str = now.strftime("%Y-%m")
        
        # 2. Cek Database Pemasukan
        sheet = get_google_sheet('Pemasukan')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        count = 1
        if not df.empty and 'Tanggal' in df.columns:
            # Filter data bulan ini
            # Asumsi kolom Tanggal format YYYY-MM-DD
            df['Tanggal'] = df['Tanggal'].astype(str)
            df_month = df[df['Tanggal'].str.startswith(current_month_str)]
            count = len(df_month) + 1 # Urutan selanjutnya
            
        # 3. Format jadi 3 digit (001, 002, dst)
        return f"{prefix}{count:03d}"
        
    except:
        # Fallback jika error / DB kosong
        return datetime.now().strftime("%y%m001")
        
# --- HELPER KONVERSI WAKTU ---
def str_to_menit(jam_str):
    """Mengubah '10:15' menjadi 615 (total menit dari jam 00:00)"""
    try:
        h, m = map(int, jam_str.split(':'))
        return h * 60 + m
    except: return 0

def menit_to_str(total_menit):
    """Mengubah 615 menjadi '10:15'"""
    h = total_menit // 60
    m = total_menit % 60
    return f"{h:02}:{m:02}"

# --- SETUP SESSION STATE ---
if 'nota_terakhir' not in st.session_state:
    st.session_state['nota_terakhir'] = None

# --- FUNGSI KONEKSI DATABASE ---
@st.cache_resource
def get_google_sheet(sheet_name):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    return client.open('TRIPL3_Barbershop_DB').worksheet(sheet_name)

# --- FUNGSI HELPER: KONTROL DISKON (BARU) ---
def get_diskon_status():
    try:
        sh = get_google_sheet('Config')
        val = sh.cell(2, 2).value # Ambil nilai di B2
        return val if val else 'UNLOCKED'
    except: return 'UNLOCKED'

def set_diskon_status(status_baru):
    try:
        sh = get_google_sheet('Config')
        sh.update_cell(2, 2, status_baru) # Update nilai B2
        st.cache_data.clear() # Hapus cache agar perubahan terbaca
        return True
    except: return False    

# --- FUNGSI AMBIL DATA LAYANAN (CLEAN DURASI) ---
@st.cache_data(ttl=600)
def get_daftar_layanan():
    try:
        sheet = get_google_sheet('Layanan')
        data = sheet.get_all_records()
        layanan_dict = {}
        for item in data:
            nama = item['Nama_Layanan']
            
            # BERSIHKAN DURASI (Ambil Angkanya Saja)
            # Contoh: "45 Menit" -> jadi 45 (int)
            durasi_raw = str(item['Durasi']).lower().replace('menit', '').replace('m', '').strip()
            try:
                durasi_int = int(durasi_raw)
            except:
                durasi_int = 45 # Default jika error
            
            layanan_dict[nama] = {
                'Harga': int(str(item['Harga']).replace('.','').replace(',','')), 
                'Durasi': durasi_int, # Simpan sebagai angka
                'Deskripsi': item['Deskripsi']
            }
        return layanan_dict
    except:
        return {
            "Triple A (Default)": {'Harga': 70000, 'Durasi': 45, 'Deskripsi': 'Standard'},
            "Triple B (Default)": {'Harga': 85000, 'Durasi': 60, 'Deskripsi': 'Wash'}
        }

# --- FUNGSI CETAK NOTA (FULL UPDATE: DISKON SUPPORT) ---
def generate_receipt_image(nama, list_items, total_normal, diskon_val, harga_final, kapster, tanggal, jam, no_nota):
    # 1. SETUP CANVAS (PENTING: JANGAN HAPUS)
    tinggi_base = 600 # Sedikit lebih panjang buat space diskon
    tinggi_per_item = 40
    H = tinggi_base + (len(list_items) * tinggi_per_item)
    W = 400
    
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img) # <--- INI YANG HILANG SEBELUMNYA
    
    # 2. LOAD FONT
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_bold = ImageFont.truetype("arialbd.ttf", 18)
        font_reg = ImageFont.truetype("arial.ttf", 16)
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_ig = ImageFont.truetype("arialbd.ttf", 16)
    except:
        font_title = ImageFont.load_default()
        font_bold = ImageFont.load_default()
        font_reg = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_ig = ImageFont.load_default()

    # 3. HEADER LOGO
    y = 20
    try:
        logo_img = Image.open("logo_struk.png") 
        base_width = 150
        w_percent = (base_width / float(logo_img.size[0]))
        h_size = int((float(logo_img.size[1]) * float(w_percent)))
        logo_img = logo_img.resize((base_width, h_size), Image.Resampling.LANCZOS)
        
        img_w, img_h = logo_img.size
        x_pos = (W - img_w) // 2
        img.paste(logo_img, (x_pos, y), logo_img if logo_img.mode == 'RGBA' else None)
        y += img_h + 10
        
    except Exception as e:
        text_bbox = draw.textbbox((0, 0), "TRIPL3 BARBERSHOP", font=font_title)
        x_pos = (W - (text_bbox[2] - text_bbox[0])) / 2
        draw.text((x_pos, y), "TRIPL3 BARBERSHOP", font=font_title, fill='black')
        y += 40

    # 4. ALAMAT & KONTAK
    def draw_centered(text, font, y_curr, color='black'):
        bbox = draw.textbbox((0, 0), text, font=font)
        w_text = bbox[2] - bbox[0]
        draw.text(((W - w_text) / 2, y_curr), text, font=font, fill=color)
        return y_curr + (bbox[3] - bbox[1]) + 5

    y = draw_centered("Komp. Citra Wisata Blok 2 No. 5", font_small, y)
    y = draw_centered("Medan Johor", font_small, y)
    y += 5
    y = draw_centered("HP/WA: 0812 6232 1355", font_small, y)
    
    y += 10
    draw.line((20, y, W-20, y), fill='black', width=2)
    y += 20

    # 5. INFO TRANSAKSI
    draw.text((30, y), f"No. Nota : {no_nota}", font=font_bold, fill='black'); y += 25
    draw.text((30, y), f"Tanggal  : {tanggal} {jam}", font=font_reg, fill='black'); y += 25
    draw.text((30, y), f"Kapster  : {kapster}", font=font_reg, fill='black'); y += 25
    draw.text((30, y), f"Customer : {nama}", font=font_reg, fill='black'); y += 30
    draw.line((20, y, W-20, y), fill='grey', width=1); y += 20

    # 6. RINCIAN ITEM
    draw.text((30, y), "Rincian:", font=font_bold, fill='black'); y += 25
    
    for item in list_items:
        nama_item = item['nama']
        if len(nama_item) > 35: nama_item = nama_item[:32] + "..."
        harga_item_fmt = f"{item['harga']:,}".replace(',', '.')
        
        draw.text((30, y), nama_item, font=font_reg, fill='black')
        
        price_bbox = draw.textbbox((0,0), harga_item_fmt, font=font_reg)
        draw.text((W - 30 - (price_bbox[2]-price_bbox[0]), y), harga_item_fmt, font=font_reg, fill='black')
        y += 30

    y += 10
    draw.line((20, y, W-20, y), fill='black', width=1); y += 15
    
    # 7. SUBTOTAL, DISKON, TOTAL (LOGIKA BARU)
    # A. Subtotal
    draw.text((30, y), "Subtotal", font=font_reg, fill='black')
    sub_fmt = f"Rp {total_normal:,}".replace(',', '.')
    sub_bbox = draw.textbbox((0,0), sub_fmt, font=font_reg)
    draw.text((W - 30 - (sub_bbox[2]-sub_bbox[0]), y), sub_fmt, font=font_reg, fill='black'); y += 25

    # B. Diskon (Hanya tampil jika ada)
    if diskon_val > 0:
        draw.text((30, y), "Diskon / Potongan", font=font_reg, fill='red')
        disc_fmt = f"- Rp {diskon_val:,}".replace(',', '.')
        disc_bbox = draw.textbbox((0,0), disc_fmt, font=font_reg)
        draw.text((W - 30 - (disc_bbox[2]-disc_bbox[0]), y), disc_fmt, font=font_reg, fill='red'); y += 25

    # C. Garis Tebal
    draw.line((20, y, W-20, y), fill='black', width=2); y += 15

    # D. TOTAL FINAL
    draw.text((30, y), "TOTAL BAYAR", font=font_title, fill='black')
    total_fmt = f"Rp {harga_final:,}".replace(',', '.')
    total_bbox = draw.textbbox((0,0), total_fmt, font=font_title)
    draw.text((W - 30 - (total_bbox[2]-total_bbox[0]), y), total_fmt, font=font_title, fill='black'); y += 60

    draw_centered("Terima Kasih!", font_bold, y); y += 30

    # 8. FOOTER INSTAGRAM
    ig_text = "tripl3.barbershop"
    bbox_ig = draw.textbbox((0,0), ig_text, font=font_ig)
    w_text_ig = bbox_ig[2] - bbox_ig[0]
    icon_size = 20
    gap = 8
    total_width = icon_size + gap + w_text_ig
    start_x = (W - total_width) / 2
    
    draw.rounded_rectangle((start_x, y, start_x + icon_size, y + icon_size), radius=5, outline="black", width=2)
    draw.ellipse((start_x + 5, y + 5, start_x + 15, y + 15), outline="black", width=2)
    draw.point((start_x + 15, y + 4), fill="black")
    draw.text((start_x + icon_size + gap, y), ig_text, font=font_ig, fill='black')
    
    return img
    
# --- FUNGSI CEK JAM (LOGIKA DURASI & INTERVAL 15 MENIT - REVISI DARIUZ) ---
def get_jam_tersedia(tanggal_pilihan, kapster_pilihan, durasi_layanan_baru, semua_layanan_db):
    try:
        # 1. SETUP JAM BUKA - TUTUP (Menit)
        # Default Jam Buka (10:00) untuk kapster umum
        JAM_BUKA_MENIT = 10 * 60  
        
        # --- REVISI KHUSUS DARIUZ HIA ---
        # Jika Dariuz, jam buka diubah jadi 14:00 (Jam 2 Siang)
        if kapster_pilihan == "Dariuz Hia":
            JAM_BUKA_MENIT = 14 * 60 
        # --------------------------------
        
        JAM_TUTUP_MENIT = 24 * 60 # 24:00
        
        # 2. AMBIL DATA BOOKING YANG SUDAH ADA
        sheet = get_google_sheet('Booking')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # List rentang waktu sibuk: [(start, end), (start, end)]
        waktu_sibuk = [] 
        
        if not df.empty:
            # Filter hanya tanggal & kapster yang dipilih, dan status bukan batal
            df = df[
                (df['Tanggal'].astype(str) == str(tanggal_pilihan)) & 
                (df['Kapster'] == kapster_pilihan) & 
                (df['Status'] != 'Batal')
            ]
            
            for _, row in df.iterrows():
                jam_mulai = str_to_menit(row['Jam'])
                
                # Cari durasi layanan dari bookingan tersebut
                # Kita harus nebak durasinya berdasarkan nama layanan di DB
                nama_lay = str(row['Layanan']).strip()
                durasi_lay = 45 # Default 45 menit jika tidak ditemukan
                
                # Cari di DB Layanan
                for db_name, db_val in semua_layanan_db.items():
                    if str(db_name).strip() == nama_lay:
                        durasi_lay = db_val['Durasi']
                        break
                
                jam_selesai = jam_mulai + durasi_lay
                waktu_sibuk.append((jam_mulai, jam_selesai))

        # 3. GENERATE SLOT PER 15 MENIT
        list_jam_valid = []
        
        # Loop dari jam buka sampai jam tutup, loncat setiap 15 menit
        for menit_start in range(JAM_BUKA_MENIT, JAM_TUTUP_MENIT, 15):
            menit_end = menit_start + durasi_layanan_baru
            
            # Cek 1: Apakah selesai melebihi jam tutup?
            if menit_end > JAM_TUTUP_MENIT:
                continue # Skip
                
            # Cek 2: Apakah Tabrakan dengan Waktu Sibuk?
            is_conflict = False
            for sibuk_start, sibuk_end in waktu_sibuk:
                # Rumus Tabrakan: 
                # (Start Baru < End Lama) DAN (End Baru > Start Lama)
                if menit_start < sibuk_end and menit_end > sibuk_start:
                    is_conflict = True
                    break
            
            if not is_conflict:
                list_jam_valid.append(menit_to_str(menit_start))

        # 4. FILTER JIKA HARI INI (Hapus jam yang sudah lewat)
        hari_ini_server = datetime.utcnow() + timedelta(hours=7)
        if str(tanggal_pilihan) == str(hari_ini_server.date()):
            menit_sekarang = hari_ini_server.hour * 60 + hari_ini_server.minute
            list_jam_valid = [j for j in list_jam_valid if str_to_menit(j) > menit_sekarang]

        return list_jam_valid

    except Exception as e:
        # Fallback jika error
        return ["14:00", "15:00", "16:00"] if kapster_pilihan == "Dariuz Hia" else ["10:00", "11:00", "12:00"]

# --- HELPERS ---
def format_nomor_wa(nomor):
    nomor = str(nomor).strip()
    if nomor.startswith("0"): return "62" + nomor[1:]
    elif nomor.startswith("62"): return nomor
    else: return "62" + nomor 

# --- DATABASE OPERATIONS ---
def simpan_booking(nama, no_wa, kapster, layanan, tgl, jam):
    try:
        sheet = get_google_sheet('Booking')
        waktu_input = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        data_baru = [str(tgl), jam, nama, str(no_wa), kapster, layanan, "Pending", waktu_input]
        sheet.append_row(data_baru)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error: {e}"); return False

# --- FUNGSI FORMAT WA KE 0 (PRIMARY KEY) ---
def format_wa_0(nomor):
    """Mengubah format apa pun (628.., 8.., 08..) menjadi 08.."""
    nomor = str(nomor).strip().replace('-', '').replace(' ', '')
    if nomor.startswith('62'):
        return '0' + nomor[2:]
    elif nomor.startswith('8'):
        return '0' + nomor
    return nomor

# --- FUNGSI FORMAT WA KE 0 (Pastikan ini ada) ---
def format_wa_0(nomor):
    # Bersihkan karakter aneh
    nomor = str(nomor).strip().replace('-', '').replace(' ', '').replace('+', '').replace('.', '')
    
    # Logika konversi
    if nomor.startswith('62'):
        return '0' + nomor[2:]
    elif nomor.startswith('8'):
        return '0' + nomor
    return nomor

# --- FUNGSI CEK DATA PELANGGAN (VERSI ANTI-GAGAL) ---
def get_data_pelanggan(wa_input):
    try:
        # 1. Format input user jadi standar "08..."
        wa_target = format_wa_0(wa_input) 
        
        sheet = get_google_sheet('Pelanggan')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty: return None

        # 2. BERSIHKAN NAMA KOLOM (Hapus spasi di header Excel)
        df.columns = df.columns.str.strip()
        
        # 3. PASTIKAN KOLOM ADA
        col_target = 'nomor_wa_0'
        if col_target not in df.columns:
            # Coba cari kolom yang mirip (antisipasi typo di excel)
            cols = df.columns.tolist()
            found = False
            for c in cols:
                if 'nomor_wa_0' in str(c).lower():
                    col_target = c
                    found = True
                    break
            if not found: return None # Nyerah kalau kolom gak ada

        # 4. NORMALISASI DATA EXCEL (KUNCI PERBAIKAN DI SINI)
        # Paksa jadi String -> Hapus spasi -> Hapus desimal (.0)
        df[col_target] = df[col_target].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        
        # Jaga-jaga: Jika Excel menyimpan "812" (tanpa 0), kita tambahkan 0
        df[col_target] = df[col_target].apply(lambda x: '0' + x if x.startswith('8') else x)

        # 5. CARI DATA
        hasil = df[df[col_target] == wa_target]
        
        if not hasil.empty:
            # Pastikan kolom nama ada
            if 'nama_pelanggan' in df.columns:
                return hasil.iloc[0]['nama_pelanggan']
            
    except Exception as e:
        print(f"Error Cari Pelanggan: {e}")
        
    return None

# --- FUNGSI UPDATE / TAMBAH PELANGGAN (VERSI STRING) ---
def sync_database_pelanggan(wa_input, nama_final, kapster_pilihan):
    try:
        sheet = get_google_sheet('Pelanggan')
        
        # Format Data
        wa_pk = format_wa_0(wa_input) # "08..."
        wa_62 = "62" + wa_pk[1:]      # "628..."
        
        # Kita baca semua dulu untuk mencari (karena .find() kadang gagal di format angka)
        # Ini lebih lambat tapi lebih akurat
        cell = None
        try:
            # Cari string "08..."
            cell = sheet.find(wa_pk)
        except:
            pass # Kalau error berarti tidak ketemu
            
        if cell:
            # --- SKENARIO UPDATE ---
            row_idx = cell.row
            # Update Nama (Kolom 4) & Kapster (Kolom 5)
            sheet.update_cell(row_idx, 4, nama_final) 
            sheet.update_cell(row_idx, 5, kapster_pilihan) 
        else:
            # --- SKENARIO INSERT ---
            # Paksa simpan sebagai string dengan tanda kutip satu (') di excel
            # Namun gspread biasanya pintar, coba simpan biasa dulu
            new_row = [wa_input, wa_62, wa_pk, nama_final, kapster_pilihan]
            sheet.append_row(new_row)
            
        return True
    except Exception as e:
        print(f"Error Sync: {e}") 
        return False

# --- GENERATOR NOMOR NOTA (LOGIKA MAX VALUE) ---
def get_next_invoice_number():
    try:
        # 1. Tentukan Prefix (Contoh: 2601 untuk Jan 2026)
        now = datetime.utcnow() + timedelta(hours=7)
        prefix_bulan = now.strftime("%y%m")  # "2601"
        current_month_dash = now.strftime("%Y-%m") # "2026-01"
        
        # 2. Ambil Data Pemasukan
        sheet = get_google_sheet('Pemasukan')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        next_sequence = 1 # Default jika belum ada transaksi bulan ini
        
        if not df.empty and 'Keterangan' in df.columns:
            # 3. Filter Data Bulan Ini (Opsional: Agar lebih cepat)
            # Kita cari yang mengandung prefix nota bulan ini di kolom Keterangan
            # Asumsi format di Keterangan: "Potong Rambut [2601005]"
            
            import re
            
            max_seq = 0
            found = False
            
            for ket in df['Keterangan']:
                # Regex untuk mencari pola angka 7 digit (YYMMXXX)
                # Mencari angka yang diawali prefix bulan ini (misal 2601...)
                match = re.search(rf'\[({prefix_bulan}(\d{{3}}))\]', str(ket))
                
                if match:
                    found = True
                    # Ambil 3 digit belakangnya (Sequence)
                    seq_str = match.group(2) 
                    seq_int = int(seq_str)
                    
                    # Bandingkan apakah ini yang paling besar?
                    if seq_int > max_seq:
                        max_seq = seq_int
            
            if found:
                next_sequence = max_seq + 1
        
        # 4. Format Hasil Akhir (Gabung Prefix + Sequence Baru)
        return f"{prefix_bulan}{next_sequence:03d}"
        
    except Exception as e:
        # Fallback Darurat (Jika error, pakai timestamp detik biar gak kembar)
        print(f"Error Generate Nota: {e}")
        return datetime.now().strftime("%y%m%H%M")

# --- FUNGSI PROSES PEMBAYARAN (FINAL FIX: KAPSTER NAME + DISKON LOGIC) ---
def proses_pembayaran(baris_ke, nama_pelanggan, list_items, metode_bayar, kapster, diskon_nominal, harga_akhir):
    try:
        sheet_booking = get_google_sheet('Booking')
        
        # 1. Update Status & No Nota di Booking
        sheet_booking.update_cell(baris_ke + 2, 7, "Selesai") 
        no_nota = get_next_invoice_number() 
        
        try:
            # Simpan No Nota, Diskon, & Harga Final ke Booking
            sheet_booking.update_cell(baris_ke + 2, 9, no_nota)
            sheet_booking.update_cell(baris_ke + 2, 11, diskon_nominal)
            sheet_booking.update_cell(baris_ke + 2, 12, harga_akhir)
        except Exception as e:
            print(f"Gagal update kolom tambahan booking: {e}")
            
        # 2. Simpan Rincian ke Sheet Pemasukan
        sheet_uang = get_google_sheet('Pemasukan')
        waktu_obj = datetime.utcnow() + timedelta(hours=7)
        tgl_skrg = waktu_obj.strftime("%Y-%m-%d")
        jam_skrg = waktu_obj.strftime("%H:%M:%S")
        
        rows_to_append = []
        
        # A. Masukkan Item Normal
        for item in list_items:
            keterangan_lengkap = f"[{no_nota}] {nama_pelanggan} ({metode_bayar}) - {kapster}"
            rows_to_append.append([
                tgl_skrg, 
                jam_skrg, 
                item['nama'], 
                keterangan_lengkap, 
                item['harga']
            ])
            
        # B. Masukkan Baris Diskon (REVISI: Ada Nama Kapster)
        if diskon_nominal > 0:
            # Kita tambahkan nama kapster di sini
            ket_diskon = f"[{no_nota}] Promo/Diskon Transaksi - {kapster}"
            
            rows_to_append.append([
                tgl_skrg, 
                jam_skrg, 
                "Potongan Diskon", 
                ket_diskon,      # <--- Sudah ada nama kapster
                -diskon_nominal  # Nilai Negatif
            ])
            
        # Kirim ke Google Sheet
        sheet_uang.append_rows(rows_to_append)
        
        return no_nota 
        
    except Exception as e:
        st.error(f"Gagal memproses pembayaran: {e}")
        return None

def batalkan_booking(baris_ke, alasan):
    try:
        sheet_booking = get_google_sheet('Booking')
        # Update Status (Kolom G / 7) menjadi "Batal"
        sheet_booking.update_cell(baris_ke + 2, 7, "Batal")
        
        # Update Alasan (Kolom J / 10) - Pastikan di Google Sheet kolom J sudah ada header "Alasan"
        # Jika kolom J belum ada, gspread biasanya otomatis mengisi ke kolom kosong berikutnya
        sheet_booking.update_cell(baris_ke + 2, 10, alasan)
        return True
    except Exception as e:
        st.error(f"Gagal membatalkan: {e}"); return False

# --- UPDATE FUNGSI PENYIMPANAN (MENERIMA LINK FOTO) ---
def simpan_transaksi_pomade(nama_pomade, nominal, keterangan, link_foto):
    try:
        # Buka Sheet Pomade
        sheet = get_google_sheet('Pomade')
        
        # Ambil Waktu
        waktu_sekarang = datetime.utcnow() + timedelta(hours=7)
        tgl_str = waktu_sekarang.strftime("%Y-%m-%d")
        jam_str = waktu_sekarang.strftime("%H:%M:%S")
        
        # Simpan 6 Kolom: Tgl, Jam, Nama, Nominal, Ket, Link
        # Pastikan di Google Sheet Anda sudah menyiapkan kolom F untuk Link
        sheet.append_row([tgl_str, jam_str, nama_pomade, nominal, keterangan, link_foto])
        
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan data ke Sheet: {e}")
        return False

# --- FUNGSI REKAP POMADE HARIAN ---
def get_rekap_pomade_harian():
    try:
        sheet = get_google_sheet('Pomade')
        data = sheet.get_all_records()
        
        if not data:
            return pd.DataFrame() # Kembalikan tabel kosong jika sheet kosong

        df = pd.DataFrame(data)

        # 1. Filter KHUSUS Hari Ini Saja
        # (Penting: Kita filter dulu sebelum kolom tanggalnya dibuang)
        waktu_skrg = datetime.utcnow() + timedelta(hours=7)
        tgl_hari_ini = waktu_skrg.strftime("%Y-%m-%d")
        
        # Pastikan header di Google Sheet Anda bernama 'Tanggal'
        df_filtered = df[df['Tanggal'] == tgl_hari_ini].copy()

        # 2. HAPUS Kolom Tanggal (Sesuai request Anda)
        # Karena ini rekap harian, tanggal pasti sama semua, jadi bisa dibuang.
        if 'Tanggal' in df_filtered.columns:
            df_filtered = df_filtered.drop(columns=['Tanggal'])
            df_filtered = df_filtered.drop(columns=['Link_Bukti'])

        # 3. (Opsional) Rapikan Urutan Kolom
        # Kita atur agar Jam muncul paling kiri. Sesuaikan nama kolom dengan header Sheet Anda.
        kolom_urut = ['Jam', 'Nama_Pomade', 'Nominal', 'Keterangan', 'Link_Bukti']
        
        # Hanya ambil kolom yang benar-benar ada di data (untuk menghindari error)
        kolom_final = [k for k in kolom_urut if k in df_filtered.columns]
        
        return df_filtered[kolom_final]

    except Exception as e:
        # st.error(f"Gagal load data: {e}") # Bisa di-uncomment untuk debugging
        return pd.DataFrame()
        
# --- FUNGSI SIMPAN PENGELUARAN (KE SHEET PENGELUARAN) ---
def simpan_pengeluaran(nama_pengeluaran, ket_tambahan, nominal):
    try:
        sheet = get_google_sheet('Pengeluaran')
        
        # Ambil Waktu Server (WIB)
        waktu_obj = datetime.utcnow() + timedelta(hours=7)
        tgl_skrg = waktu_obj.strftime("%Y-%m-%d")
        jam_skrg = waktu_obj.strftime("%H:%M:%S") # Format Jam:Menit:Detik
        
        # Simpan 5 Kolom: [Tanggal, Waktu, Item, Keterangan, Nominal]
        data_baru = [tgl_skrg, jam_skrg, nama_pengeluaran, ket_tambahan, nominal]
        sheet.append_row(data_baru)
        return True
    except: return False

# --- UI UTAMA ---
menu = st.sidebar.selectbox("Pilih Mode Aplikasi", ["Booking Pelanggan", "Halaman Kasir", "Owner Insight"])

# 1. BOOKING PELANGGAN
if menu == "Booking Pelanggan":
    st.title("💈TRIPL3 Barbershop")
    
    # --- PEMBERSIH FORM ---
    # Logika: Jika ada bendera 'sukses_reset', paksa kosongkan semua input
    if st.session_state.get('sukses_reset', False):
        st.session_state['wa_input_user'] = ""       # Kosongkan WA
        st.session_state['nama_pelanggan_input'] = "" # Kosongkan Nama
        st.session_state['nama_auto'] = ""           # Kosongkan Data Auto
        st.session_state['last_wa_checked'] = ""     # Reset pengecekan WA
        st.session_state['sukses_reset'] = False     # Matikan bendera
    # ---------------------------------
    
    # Ambil Data Layanan Terbaru dari DB
    DATA_LAYANAN = get_daftar_layanan()
    
    col_kiri, col_kanan = st.columns([1, 2])
    
    with col_kiri:
        # ... (Kode di atas: st.title, dll) ...

    # --- PERSIAPAN DATA KAPSTER ---
    # Pastikan urutan nama ini SAMA PERSIS dengan urutan foto/kolom Anda
        list_kapster = ["Dariuz Hia", "David", "Herry"] 
    
# --- 1. PILIH KAPSTER (LOGIKA ACAK/DINAMIS) ---
    if 'default_kapster_index' not in st.session_state:
        st.session_state['default_kapster_index'] = random.randint(0, len(list_kapster) - 1)

    kapster = st.selectbox(
        "Pilih Kapster", 
        list_kapster, 
        index=st.session_state['default_kapster_index'],
        key="pilihan_kapster"
    )

    # --- 2. MEMBAGI LAYAR JADI 2 KOLOM (KIRI: FOTO, KANAN: FORM) ---
    col_kiri, col_kanan = st.columns([1, 2]) # [1, 2] artinya kolom kanan 2x lebih lebar

    # --- 3. ISI KOLOM KIRI (FOTO) ---
    with col_kiri:
        file_foto = INFO_KAPSTER[kapster]['img']
        
        # Cek apakah file foto ada di folder?
        if os.path.exists(file_foto):
            st.image(file_foto, width=200, use_container_width=True)
        else:
            # Gambar cadangan jika file tidak ditemukan
            st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png", caption="Foto belum tersedia", width=150)
            
    # --- 4. ISI KOLOM KANAN (FORM & INFO) ---
    with col_kanan:
        st.subheader(f"Profil: {kapster}")
        st.info(INFO_KAPSTER[kapster]['deskripsi'])
        st.write("---")
        
        # PILIH LAYANAN (Pakai Data dari DB)
        layanan_pilihan = st.selectbox("Pilih Layanan", list(DATA_LAYANAN.keys()))
        
        # Tampilkan Detail Layanan (Deskripsi, Harga, Durasi)
        detail = DATA_LAYANAN[layanan_pilihan]
        st.markdown(f"**⏱️ Durasi:** {detail['Durasi']} Menit") 
        st.caption(f"📝 *Include: {detail['Deskripsi']}*")

        # Input Tanggal
        hari_ini_wib = (datetime.utcnow() + timedelta(hours=7)).date()
        tgl = st.date_input("Tanggal Booking", hari_ini_wib, format="DD/MM/YYYY")
        st.caption(f"📅 Pilihan: **{tanggal_indo(tgl)}**")
                            
        # --- UPDATE CARA PANGGIL JAM ---
        # Kita masukkan Durasi Layanan Pilihan User & Database Lengkap
        durasi_user = detail['Durasi']
        jam_tersedia = get_jam_tersedia(tgl, kapster, durasi_user, DATA_LAYANAN)
        # -------------------------------
        
        if not jam_tersedia:
            st.warning("⚠️ Jadwal Penuh untuk layanan ini.")
            jam = st.selectbox("Jam", ["Penuh"], disabled=True)
            tombol_aktif = False
        else:
            jam = st.selectbox("Pilih Jam (Interval 15 Menit)", jam_tersedia)
            tombol_aktif = True
   
    # BATAS AKHIR KOLOM C1 & C2 (Setelah pemilihan Jam)
    st.write("---") 
    st.subheader("Data Diri Pemesan")

    # 1. INPUT WA
    wa = st.text_input("Nomor WhatsApp (Wajib)", placeholder="Contoh: 0812...", key="wa_input_user")

    # Variabel penampung notifikasi (agar bisa ditaruh di bawah nama)
    pesan_notifikasi = None
    tipe_notifikasi = ""

    # --- LOGIKA OTOMATISASI NAMA ---
    if 'last_wa_checked' not in st.session_state:
        st.session_state['last_wa_checked'] = ""
    
    # Cek jika nomor WA berubah dari sebelumnya
    if wa and wa != st.session_state['last_wa_checked']:
        with st.spinner("Mengecek data pelanggan..."):
            nama_di_db = get_data_pelanggan(wa)
            
            if nama_di_db:
                # Update Session State Nama
                st.session_state['nama_pelanggan_input'] = nama_di_db
                
                # Simpan Pesan untuk ditampilkan nanti
                pesan_notifikasi = f"Hey Bro {nama_di_db}, Selamat datang kembali! 🤝"
                tipe_notifikasi = "success"
            else:
                # Kosongkan nama jika nomor baru
                if 'nama_pelanggan_input' in st.session_state:
                     st.session_state['nama_pelanggan_input'] = ""
                
                # Simpan Pesan
                pesan_notifikasi = "Hello our new customer! Silakan isi nama Kamu ya. 😊"
                tipe_notifikasi = "info"
        
        # Simpan nomor ini agar tidak dicek berulang-ulang
        st.session_state['last_wa_checked'] = wa

    # 2. INPUT NAMA
    nama = st.text_input("Nama Pelanggan", placeholder="Nama Anda...", key="nama_pelanggan_input")
    
    # 3. TAMPILKAN NOTIFIKASI DI BAWAH KOLOM NAMA (POSISI STRATEGIS)
    if pesan_notifikasi:
        if tipe_notifikasi == "success":
            st.success(pesan_notifikasi, icon="✅")
        else:
            st.info(pesan_notifikasi, icon="👋")
    
    st.write("---")

    # 4. TOMBOL BOOKING
    if st.button("Booking Sekarang", type="primary", disabled=not tombol_aktif, use_container_width=True):
        if nama and wa and jam != "Penuh":
            with st.spinner("Sedang Mendaftarkan Booking..."):
                
                # A. SIMPAN KE SHEET BOOKING
                sukses_booking = simpan_booking(nama, wa, kapster, layanan_pilihan, tgl, jam)
                
                if sukses_booking:
                    # B. UPDATE DATABASE PELANGGAN
                    sync_database_pelanggan(wa, nama, kapster)
                    
                    # ... (Kode Simpan & Update Database di atasnya biarkan sama) ...
                    
                    # ... (Kode A & B di atasnya biarkan sama) ...
                    
                    # ... (Kode di atasnya tetap sama) ...
                    
                    # C. RESET & SUKSES
                    st.success(f"✅ Booking Berhasil! Sampai jumpa {nama}.")
                    st.snow()
                    
                    # --- NYALAKAN BENDERA RESET ---
                    st.session_state['sukses_reset'] = True 
                    
                    time.sleep(3)
                    st.rerun()
        else: st.warning("Mohon lengkapi Nama dan No WA.")

# 2. HALAMAN KASIR (Admin)
# ==========================================
elif menu == "Halaman Kasir":
    st.title("💼 Dashboard Kasir")
    password = st.sidebar.text_input("Password", type="password")
        
    DATA_LAYANAN = get_daftar_layanan() 

    if password == "admin123":
        st.sidebar.success("Login Berhasil")
        
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔴 Antrian & Bayar", "✅ Riwayat", "💰 Pengeluaran", "📊 Lapor Bos", "🏆 Mingguan", "🧴 Pomade"])
        
        # --- TAB 1: ANTRIAN & BAYAR (DENGAN FITUR DISKON) ---
        with tab1:
            # A. BAGIAN DOWNLOAD NOTA (JIKA TRANSAKSI SELESAI)
            if st.session_state['nota_terakhir'] is not None:
                data_nota = st.session_state['nota_terakhir']
                st.success("✅ Transaksi Selesai!")
                
                c_img, c_act = st.columns([1, 1.5])
                with c_img: st.image(data_nota['img'], width=250)
                
                with c_act:
                    buf = io.BytesIO(); data_nota['img'].save(buf, format="PNG"); byte_im = buf.getvalue()
                    st.download_button("⬇️ 1. Download Nota", byte_im, f"Nota_{data_nota['nama']}.png", "image/png")
                    
                    hp_fmt = format_nomor_wa(data_nota['wa'])
                    rincian_text = ""
                    for it in data_nota['items']:
                        rincian_text += f"• {it['nama']} (Rp {it['harga']:,})\n"
                    
                    # Tambahkan info diskon di pesan WA jika ada
                    pesan_tambahan = ""
                    if 'diskon' in data_nota and data_nota['diskon'] > 0:
                         pesan_tambahan = f"\n(Diskon: -Rp {data_nota['diskon']:,})\n*Total Bayar: Rp {data_nota['total_final']:,}*"

                    pesan_nota = (
                        f"Hey Bro *{data_nota['nama']}*! 👋\n"
                        f"Terima kasih sudah mampir di *TRIPL3 Barbershop*.\n\n"
                        f"{pesan_tambahan}\n"
                        f"You look sharp! See you next time. 💈"
                    )
                    link_wa_nota = f"https://wa.me/{hp_fmt}?text={urllib.parse.quote(pesan_nota)}"
                    st.link_button("💬 2. Chat Pengantar Nota", link_wa_nota)
                    
                    st.write("---")
                    if st.button("Tutup / Transaksi Baru"): st.session_state['nota_terakhir'] = None; st.rerun()

            # B. MODAL KERJA KASIR
            else:
                if st.button("🔄 Refresh Data Antrian"): st.rerun()
                
                # ============================================================
                # BAGIAN 1: ANTRIAN REGULER (PRIORITAS UTAMA)
                # ============================================================
                st.subheader("📋 Daftar Antrian Booking")
                
                try:
                    sheet = get_google_sheet('Booking')
                    data = sheet.get_all_records()
                    df = pd.DataFrame(data)
                    
                    if not df.empty:
                        df.columns = df.columns.str.strip()
                        if 'Waktu' in df.columns and 'Jam' not in df.columns:
                            df.rename(columns={'Waktu': 'Jam'}, inplace=True)
                    
                    if not df.empty and 'Status' in df.columns and 'Jam' in df.columns:
                        df_pending = df[df['Status'] == 'Pending'].reset_index()
                        
                        if not df_pending.empty:
                            df_tampil = df_pending[['Tanggal', 'Jam', 'Nama_Pelanggan', 'Layanan', 'Kapster']].copy()
                            df_tampil['Tanggal'] = df_tampil['Tanggal'].apply(tanggal_indo)
                            df_tampil.index = range(1, len(df_tampil) + 1)
                            st.dataframe(df_tampil, use_container_width=True)
                            
                            pilihan_list = []
                            for i, row in df_pending.iterrows():
                                tgl_cantik = tanggal_indo(row['Tanggal'])
                                label = f"{tgl_cantik} | {row['Jam']} - {row['Nama_Pelanggan']} ({row['Kapster']})"
                                pilihan_list.append((row['index'], label, row['Layanan'], row['Nama_Pelanggan'], row['No_WA'], row['Jam'], row['Kapster'], row['Tanggal']))
                            
                            pilihan = st.selectbox("Pilih Pelanggan:", pilihan_list, format_func=lambda x: x[1])
                            
                            if pilihan:
                                idx, label, lay_awal, nam, no_hp, jam_bk, kap, tgl_bk = pilihan
                                st.info(f"🔒 **Layanan Utama:** {lay_awal}")
                                
                                # --- UPGRADE SECTION ---
                                st.markdown("#### 🚀 Upgrade Layanan (Opsional)")
                                cek_upgrade = st.checkbox("Pelanggan ganti ke paket lebih mahal?")
                                item_upgrade_diff = None 
                                nama_layanan_final = lay_awal
                                
                                if cek_upgrade:
                                    opsi_up = list(DATA_LAYANAN.keys())
                                    if lay_awal in opsi_up: opsi_up.remove(lay_awal)
                                    col_up1, col_up2 = st.columns([2, 1])
                                    with col_up1: target_upgrade = st.selectbox("Upgrade menjadi:", opsi_up)
                                    
                                    harga_awal = 0; harga_akhir = 0
                                    for db_n, db_v in DATA_LAYANAN.items():
                                        if str(db_n).strip() == str(lay_awal).strip(): harga_awal = db_v['Harga']; break
                                    harga_akhir = DATA_LAYANAN[target_upgrade]['Harga']
                                    selisih = harga_akhir - harga_awal
                                    
                                    with col_up2:
                                        if selisih > 0:
                                            st.success(f"➕ Tambah: Rp {selisih:,}")
                                            nama_layanan_final = f"{target_upgrade} (Up from {lay_awal})"
                                            item_upgrade_diff = {'nama': "Biaya Upgrade Layanan", 'harga': selisih}
                                        elif selisih == 0: st.warning("Harga sama.")
                                        else: st.error("⛔ Dilarang Downgrade!")

                                st.markdown("#### 🧴 Tambahan Lain")
                                opsi_addon = list(DATA_LAYANAN.keys())
                                if lay_awal in opsi_addon: opsi_addon.remove(lay_awal)
                                if cek_upgrade and target_upgrade in opsi_addon: opsi_addon.remove(target_upgrade)
                                layanan_tambahan = st.multiselect("Pilih item tambahan:", opsi_addon)
                                
                                list_belanja = []
                                total_tagihan_normal = 0
                                harga_base = 0
                                for db_n, db_v in DATA_LAYANAN.items():
                                    if str(db_n).strip() == str(lay_awal).strip(): harga_base = db_v['Harga']; break
                                list_belanja.append({'nama': f"Jasa {nama_layanan_final}", 'harga': harga_base})
                                total_tagihan_normal += harga_base
                                if item_upgrade_diff:
                                    list_belanja.append(item_upgrade_diff); total_tagihan_normal += item_upgrade_diff['harga']
                                for tamb in layanan_tambahan:
                                    h_tamb = DATA_LAYANAN[tamb]['Harga']
                                    list_belanja.append({'nama': f"Add-on {tamb}", 'harga': h_tamb})
                                    total_tagihan_normal += h_tamb
                                
                                st.write("---")
                                c1, c2, c3 = st.columns([1, 1.5, 1])
                                with c1:
                                    st.caption("📢 Info & Reminder:")
                                    pesan_wa = (f"Hey Bro *{nam}*, reminder booking jam *{jam_bk}*. See you! 💈")
                                    st.link_button("💬 Chat Reminder", f"https://wa.me/{format_nomor_wa(no_hp)}?text={urllib.parse.quote(pesan_wa)}")
                                    st.write("---")
                                    st.caption(f"🛒 Rincian ({len(list_belanja)} Item):")
                                    for item in list_belanja: st.text(f"- {item['nama']}")
                                
                                with c2:
                                    # --- CEK STATUS DARI OWNER (BARU) ---
                                    status_izin = get_diskon_status()
                                    nominal_diskon = 0 
                                    
                                    if status_izin == 'UNLOCKED':
                                        # JIKA DIBUKA: TAMPILKAN MENU DISKON
                                        st.markdown("##### 🏷️ Diskon / Potongan")
                                        jenis_disc = st.radio("Tipe Diskon", ["Tanpa Diskon", "Rupiah (Rp)", "Persen (%)"], horizontal=True, label_visibility="collapsed")
                                        
                                        if jenis_disc == "Rupiah (Rp)":
                                            val_rp = st.number_input("Nominal Potongan", min_value=0, step=1000)
                                            nominal_diskon = val_rp
                                        elif jenis_disc == "Persen (%)":
                                            val_pct = st.number_input("Persentase (%)", min_value=0, max_value=100, step=5)
                                            nominal_diskon = total_tagihan_normal * (val_pct / 100)
                                    else:
                                        # JIKA DIKUNCI: SEMBUNYIKAN / TAMPILKAN PESAN
                                        st.markdown("##### 🏷️ Diskon")
                                        st.info("🔒 Fitur diskon dikunci Owner.")
                                        nominal_diskon = 0
                                    
                                    # Hitung Total Akhir
                                    total_final = total_tagihan_normal - nominal_diskon
                                    if total_final < 0: total_final = 0
                                    
                                    # Tampilan Angka
                                    if nominal_diskon > 0:
                                        st.caption(f"Harga Normal: Rp {total_tagihan_normal:,}")
                                        st.caption(f"Diskon: - Rp {int(nominal_diskon):,}")
                                        st.markdown(f"#### Total Akhir: Rp {int(total_final):,}")
                                    else:
                                        st.metric("Total Tagihan", f"Rp {total_tagihan_normal:,}")
                                    
                                    st.write("---")
                                    # ... (Lanjut ke tombol metode bayar dst) ...
                                    metode = st.radio("Metode Bayar:", ["Tunai", "QRIS"], horizontal=True)
                                    
                                    tombol_aman = True
                                    if cek_upgrade and selisih < 0: tombol_aman = False
                                    
                                    if tombol_aman and total_final >= 0:
                                        if st.button("✅ Bayar & Cetak", type="primary"):
                                            nama_simpan = nam
                                            if item_upgrade_diff: nama_simpan = f"{nam} [UPGRADE]"
                                            
                                            # CALL FUNGSI PROSES PEMBAYARAN (DENGAN DISKON)
                                            no_nota_hasil = proses_pembayaran(idx, nama_simpan, list_belanja, metode, kap, int(nominal_diskon), int(total_final))
                                            
                                            if no_nota_hasil:
                                                # CALL FUNGSI GAMBAR (DENGAN DISKON)
                                                img = generate_receipt_image(nam, list_belanja, total_tagihan_normal, int(nominal_diskon), int(total_final), kap, tgl_bk, jam_bk, no_nota_hasil)
                                                
                                                st.session_state['nota_terakhir'] = {
                                                    'img': img, 
                                                    'nama': nam, 
                                                    'wa': no_hp, 
                                                    'items': list_belanja,
                                                    'total_normal': total_tagihan_normal,
                                                    'diskon': int(nominal_diskon),
                                                    'total_final': int(total_final)
                                                }
                                                st.cache_data.clear(); st.rerun()
                                    elif not tombol_aman: st.error("Perbaiki pilihan upgrade.")
                                    
                                with c3:
                                    with st.popover("❌ Batal"):
                                        st.write(f"Batalkan {nam}?")
                                        alasan_batal = st.text_input("Alasan (Wajib diisi)", placeholder="No Show / Reschedule")
                                        if st.button("Ya, Hapus Antrian"):
                                            if alasan_batal:
                                                if batalkan_booking(idx, alasan_batal):
                                                    st.toast("Berhasil dibatalkan!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                                            else: st.error("Isi alasan dulu.")
                        else: st.info("Tidak ada antrian booking.")
                    else: st.warning("Data Booking kosong.")
                except Exception as e: st.error(f"Error: {e}")

                st.write("---")

                # ============================================================
                # BAGIAN 2: JALUR CEPAT (GO SHOW / WALK-IN)
                # ============================================================
                with st.expander("⚡ Transaksi Langsung (Go Show / Tanpa Booking)", expanded=False):
                    st.caption("Menu ini hanya digunakan ketika pelanggan datang langsung dan jadwal kapster di halaman pelanggan tidak tersedia.")
                    
                    if st.session_state.get('reset_go_show', False):
                        st.session_state['go_wa'] = ""
                        st.session_state['go_nama'] = ""
                        st.session_state['go_last_wa'] = ""
                        st.session_state['reset_go_show'] = False

                    # 1. INPUT WA
                    go_wa = st.text_input("No WA Pelanggan (Tekan Enter untuk Cek)", key="go_wa")
                    if 'go_last_wa' not in st.session_state: st.session_state['go_last_wa'] = ""

                    if go_wa and go_wa != st.session_state['go_last_wa']:
                        with st.spinner("Mengecek data..."):
                            hasil_nama = get_data_pelanggan(go_wa)
                            if hasil_nama: st.session_state['go_nama'] = hasil_nama 
                            else:
                                st.info("ℹ️ Pelanggan Baru. Silakan input nama manual.")
                                st.session_state['go_nama'] = "" 
                        st.session_state['go_last_wa'] = go_wa

                    # 2. INPUT NAMA
                    go_nama = st.text_input("Nama Pelanggan", key="go_nama")
                    
                    c_go1, c_go2 = st.columns(2)
                    with c_go1:
                        go_kapster = st.selectbox("Pilih Kapster", list(INFO_KAPSTER.keys()), key="go_kapster")
                        go_layanan = st.selectbox("Pilih Layanan", list(DATA_LAYANAN.keys()), key="go_layanan")
                    
                    with c_go2:
                        opsi_go_addon = list(DATA_LAYANAN.keys())
                        if go_layanan in opsi_go_addon: opsi_go_addon.remove(go_layanan)
                        go_addon = st.multiselect("Tambahan (Opsional)", opsi_go_addon, key="go_addon")
                        go_metode = st.radio("Metode Bayar", ["Tunai", "QRIS"], horizontal=True, key="go_metode")

                    # Hitung Total
                    go_total_normal = 0
                    go_items = []
                    
                    hrg_utama = 0
                    for db_n, db_v in DATA_LAYANAN.items():
                        if str(db_n).strip() == str(go_layanan).strip(): hrg_utama = db_v['Harga']; break
                    go_items.append({'nama': f"Jasa {go_layanan}", 'harga': hrg_utama})
                    go_total_normal += hrg_utama
                    
                    for add in go_addon:
                        h_add = DATA_LAYANAN[add]['Harga']
                        go_items.append({'nama': f"Add-on {add}", 'harga': h_add})
                        go_total_normal += h_add
                                       
                    # --- INPUT DISKON GO SHOW (DENGAN CEK STATUS) ---
                    st.write("---")
                    
                    status_izin_go = get_diskon_status()
                    go_nominal_diskon = 0
                    
                    if status_izin_go == 'UNLOCKED':
                        c_disc1, c_disc2 = st.columns([1, 1])
                        with c_disc1:
                            go_jenis_disc = st.radio("Diskon", ["Tanpa Diskon", "Rupiah", "Persen"], horizontal=True, key="go_type_disc")
                        
                        if go_jenis_disc == "Rupiah":
                            with c_disc2: go_nominal_diskon = st.number_input("Nominal Potongan", min_value=0, step=1000, key="go_val_rp")
                        elif go_jenis_disc == "Persen":
                            with c_disc2: 
                                go_pct = st.number_input("Persentase (%)", min_value=0, max_value=100, step=5, key="go_val_pct")
                                go_nominal_diskon = go_total_normal * (go_pct / 100)
                    else:
                        st.info("🔒 Fitur Diskon Dikunci Owner")
                        go_nominal_diskon = 0

                    go_total_final = go_total_normal - go_nominal_diskon
                    if go_total_final < 0: go_total_final = 0
                    
                    # ... (Setelah logika perhitungan go_total_final) ...
                    
                    go_total_final = go_total_normal - go_nominal_diskon
                    if go_total_final < 0: go_total_final = 0
                    
                    # --- TAMPILAN TOTAL DENGAN DISKON (UPDATE) ---
                    # Format: Total Akhir (Normal: 100.000 | Disc: 10.000)
                    st.markdown(f"""
                    **Total Akhir: Rp {int(go_total_final):,}** *(Normal: {int(go_total_normal):,} | Potongan: {int(go_nominal_diskon):,})*
                    """.replace(',', '.'))
                    
                    if st.button("Proses Transaksi Langsung", type="primary"):
                        if go_nama and go_wa:
                            with st.spinner("Memproses..."):
                                sync_database_pelanggan(go_wa, go_nama, go_kapster)

                                now_obj = datetime.utcnow() + timedelta(hours=7)
                                tgl_go = now_obj.strftime("%Y-%m-%d")
                                jam_go = now_obj.strftime("%H:%M")
                                
                                try:
                                    sheet_bk = get_google_sheet('Booking')
                                    waktu_input = now_obj.strftime("%Y-%m-%d %H:%M:%S")
                                    # Append data
                                    sheet_bk.append_row([tgl_go, jam_go, go_nama, format_wa_0(go_wa), go_kapster, go_layanan, "Proses..", waktu_input, ""])
                                    
                                    all_vals = sheet_bk.get_all_values()
                                    last_row_idx = len(all_vals)
                                    idx_untuk_fungsi = last_row_idx - 2
                                    
                                    # CALL FUNGSI PROSES (DENGAN DISKON)
                                    no_nota_hasil = proses_pembayaran(idx_untuk_fungsi, go_nama, go_items, go_metode, go_kapster, int(go_nominal_diskon), int(go_total_final))
                                    
                                    if no_nota_hasil:
                                        # CALL FUNGSI GAMBAR (DENGAN DISKON)
                                        img = generate_receipt_image(go_nama, go_items, go_total_normal, int(go_nominal_diskon), int(go_total_final), go_kapster, tgl_go, jam_go, no_nota_hasil)
                                        
                                        st.session_state['reset_go_show'] = True
                                        
                                        st.session_state['nota_terakhir'] = {
                                            'img': img, 
                                            'nama': go_nama, 
                                            'wa': go_wa, 
                                            'items': go_items,
                                            'total_normal': go_total_normal,
                                            'diskon': int(go_nominal_diskon),
                                            'total_final': int(go_total_final)
                                        }
                                        st.cache_data.clear(); st.rerun()
                                        
                                except Exception as e:
                                    st.error(f"Gagal proses Go Show: {e}")
                        else:
                            st.warning("Nama dan WA wajib diisi.")
        
        # --- TAB 2: RIWAYAT & CETAK ULANG (VERSI RINGKAS - KHUSUS NO NOTA) ---
        with tab2:
            st.header("✅ Riwayat & Cetak Ulang")
            
            try:
                # 1. AMBIL DATA BOOKING
                sheet = get_google_sheet('Booking')
                data = sheet.get_all_records()
                df = pd.DataFrame(data)
                
                if not df.empty:
                    # Adaptasi Nama Kolom (Jaga-jaga)
                    if 'Waktu' in df.columns and 'Jam' not in df.columns:
                        df.rename(columns={'Waktu': 'Jam'}, inplace=True)
                    
                    if 'Jam' in df.columns and 'Tanggal' in df.columns:
                        # Filter Tanggal & Sortir
                        col_tgl1, col_tgl2 = st.columns([1, 2])
                        with col_tgl1: tgl_filter = st.date_input("Pilih Tanggal", datetime.now())
                        
                        df_filtered = df[df['Tanggal'].astype(str) == str(tgl_filter)].copy()
                        if not df_filtered.empty:
                            df_filtered = df_filtered.sort_values(by='Jam', ascending=False)
                            
                            # --- TAMBAHAN: Buat Nomor Urut (Mulai dari 1) ---
                            df_filtered.insert(0, 'No', range(1, len(df_filtered) + 1))
                            # -----------------------------------------------

                            if 'No_WA' in df_filtered.columns: df_filtered['No_WA'] = df_filtered['No_WA'].apply(format_wa_0)

                            # Tampilkan Tabel (Tambahkan 'No' di list kolom)
                            cols_target = ['No', 'Jam', 'Nama_Pelanggan', 'No_WA', 'Layanan', 'Kapster', 'Status', 'No_Nota']
                            cols = [k for k in cols_target if k in df_filtered.columns]
                            
                            st.dataframe(df_filtered[cols], use_container_width=True, hide_index=True)
                            st.write("---")
                            
                            # --- BAGIAN CETAK ULANG (SIMPLE) ---
                            st.subheader("🖨️ Cetak Ulang Struk")
                            
                            # Filter Selesai
                            df_siap = df_filtered[df_filtered.get('Status') == 'Selesai'].reset_index() if 'Status' in df_filtered.columns else df_filtered.reset_index()
                            
                            if not df_siap.empty:
                                opsi = []
                                for i, row in df_siap.iterrows():
                                    # Cek No Nota
                                    nota_txt = f"[{row['No_Nota']}] " if 'No_Nota' in row and str(row['No_Nota']).strip() else "[LAMA] "
                                    label = f"{nota_txt}{row['Jam']} - {row['Nama_Pelanggan']}"
                                    opsi.append((i, label))
                                
                                pilihan = st.selectbox("Pilih Transaksi:", opsi, format_func=lambda x: x[1])
                                
                                # --- GANTI DARI BARIS INI KE BAWAH ---
                                if pilihan and st.button("Cetak Struk"):
                                    idx_sel, _ = pilihan
                                    d_row = df_siap.iloc[idx_sel]
                                    
                                    # 1. CEK NO NOTA
                                    no_nota = str(d_row.get('No_Nota', '')).strip()
                                    if not no_nota:
                                        st.error("⚠️ Transaksi Lama (Tanpa Nota). Tidak bisa dicetak.")
                                    else:
                                        # 2. AMBIL ITEM DARI PEMASUKAN
                                        items = []
                                        total = 0
                                        with st.spinner("Menyiapkan struk..."):
                                            try:
                                                sheet_uang = get_google_sheet('Pemasukan')
                                                df_uang = pd.DataFrame(sheet_uang.get_all_records())
                                                
                                                if not df_uang.empty:
                                                    # Cari item berdasarkan [No_Nota]
                                                    df_match = df_uang[df_uang['Keterangan'].str.contains(f"[{no_nota}]", regex=False, na=False)]
                                                    for _, r in df_match.iterrows():
                                                        nom = int(str(r['Nominal']).replace('.','').replace(',',''))
                                                        items.append({'nama': r['Item'], 'harga': nom})
                                                        total += nom
                                            except: pass
                                            
                                            # Fallback jika kosong
                                            if not items:
                                                items = [{'nama': f"Layanan {d_row['Layanan']}", 'harga': 0}]
                                                st.caption("⚠️ Detail item tidak ditemukan, menggunakan data default.")
    
                                        # 3. GENERATE GAMBAR (SOLUSI FINAL: SEMUA PAKAI NAMA)
                                        # Kita panggil dengan menyebut nama parameternya satu per satu
                                        # agar tidak ada yang tertukar atau dianggap hilang.
                                        try:
                                            # Pastikan kita ambil tanggal dari row data
                                            tgl_fix = str(d_row['Tanggal']) if 'Tanggal' in d_row else str(datetime.now().date())
                                            
                                            img = generate_receipt_image(
                                                nama_plg = d_row['Nama_Pelanggan'],
                                                items = items,
                                                total = total,       
                                                kapster = d_row['Kapster'],    # <--- Kita sebut namanya
                                                tanggal = tgl_fix,             # <--- Kita sebut namanya
                                                jam = str(d_row['Jam']),       # <--- Kita sebut namanya
                                                no_nota = no_nota              # <--- Kita sebut namanya
                                            )
                                            
                                            # TAMPILKAN HASIL
                                            c1, c2 = st.columns([1, 1.5])
                                            c1.image(img, caption=f"Struk {no_nota}", width=250)
                                            
                                            buf = io.BytesIO()
                                            img.save(buf, format="PNG")
                                            byte_im = buf.getvalue()
                                            
                                            c2.download_button(
                                                label="⬇️ Download Struk PNG",
                                                data=byte_im,
                                                file_name=f"Struk_{no_nota}.png",
                                                mime="image/png"
                                            )
                                        except TypeError as te:
                                            st.error(f"Masih ada ketidakcocokan nama: {te}")
                                            st.info("Coba cek fungsi 'def generate_receipt_image' di bagian paling atas kode app.py Anda. Pastikan nama argumennya sama persis dengan yang ditulis di atas (nama_plg, items, total, kapster, tanggal, jam, no_nota).")
                            else: st.info("Belum ada transaksi selesai hari ini.")
                        else: st.info("Tidak ada data.")
                else: st.info("Data kosong.")
            except Exception as e: st.error(f"Error: {e}")
            
        # --- TAB 3: INPUT PENGELUARAN ---
        with tab3:
            st.header("💰 Catat Pengeluaran")
            
            list_rekomendasi = ["Laundry Handuk", "Token Listrik"]
            
            try:
                # BACA DARI SHEET PENGELUARAN
                sheet_out = get_google_sheet('Pengeluaran')
                data_out = sheet_out.get_all_records()
                df_out = pd.DataFrame(data_out)
                
                if not df_out.empty:
                    # Ambil kolom 'Item' untuk rekomendasi
                    if 'Item' in df_out.columns:
                        history_items = df_out['Item'].unique().tolist()
                        list_rekomendasi = sorted(list(set(list_rekomendasi + history_items)))
            except: pass 
            
            list_rekomendasi.insert(0, "📝 Input Nama Baru...")
            
            # ... (SISA KODE KE BAWAH: FORM INPUT & TOMBOL SIMPAN, TIDAK PERLU DIUBAH) ...
            # ... (Tinggal copy-paste bagian form input dari kode sebelumnya) ...
            pilih_nama = st.selectbox("1. Nama Pengeluaran (Ketik untuk cari)", list_rekomendasi, index=1)
            
            nama_final = ""
            if pilih_nama == "📝 Input Nama Baru...":
                nama_final = st.text_input("👉 Ketik Nama Pengeluaran Baru", placeholder="Contoh: Servis AC")
            else: nama_final = pilih_nama

            nominal = st.number_input("2. Nominal (Rp)", min_value=0, step=1000)
            ket_bebas = st.text_input("3. Keterangan Tambahan (Opsional)", placeholder="Contoh: 5 Kg, Warna Biru, dll")
            
            st.write("---")
            if st.button("Simpan Pengeluaran", type="primary"):
                if nama_final and nominal > 0:
                    if simpan_pengeluaran(nama_final, ket_bebas, nominal):
                        st.success("✅ Disimpan!"); st.cache_data.clear(); time.sleep(1.5); st.rerun()
                else: st.warning("Isi data lengkap.")
        
        with tab4:
            st.header("📊 Lapor Bos")
            st.caption("Pilih tanggal, cek data, lalu kirim rekap lengkap ke WA.")
            
            # 1. PILIH TANGGAL
            now_wib = datetime.utcnow() + timedelta(hours=7)
            tgl_laporan = st.date_input("Pilih Tanggal Laporan:", now_wib)
            tgl_str = tgl_laporan.strftime("%Y-%m-%d")
            
            st.write("---")

            if st.button(f"Hitung Rekap Tanggal {tanggal_indo(tgl_laporan)}"):
                try:
                    # --- A. AMBIL DATA KEUANGAN ---
                    df_masuk_today = pd.DataFrame()
                    df_keluar_today = pd.DataFrame()
                    
                    try:
                        sheet_in = get_google_sheet('Pemasukan')
                        data_in = sheet_in.get_all_records()
                        df_in = pd.DataFrame(data_in)
                        if not df_in.empty:
                            df_in['Tanggal'] = df_in['Tanggal'].astype(str)
                            df_masuk_today = df_in[df_in['Tanggal'] == tgl_str]
                    except: pass

                    try:
                        sheet_out = get_google_sheet('Pengeluaran')
                        data_out = sheet_out.get_all_records()
                        df_out = pd.DataFrame(data_out)
                        if not df_out.empty:
                            df_out['Tanggal'] = df_out['Tanggal'].astype(str)
                            df_keluar_today = df_out[df_out['Tanggal'] == tgl_str]
                    except: pass
                    
                    # --- B. AMBIL DATA BOOKING (STATISTIK) ---
                    df_booking_today = pd.DataFrame()
                    try:
                        sheet_bk = get_google_sheet('Booking')
                        data_bk = sheet_bk.get_all_records()
                        df_bk = pd.DataFrame(data_bk)
                        
                        if not df_bk.empty:
                            df_bk.columns = df_bk.columns.str.strip()
                            if 'Waktu' in df_bk.columns and 'Jam' not in df_bk.columns:
                                df_bk.rename(columns={'Waktu': 'Jam'}, inplace=True)
                            
                            df_bk['Tanggal'] = df_bk['Tanggal'].astype(str)
                            df_booking_today = df_bk[
                                (df_bk['Tanggal'] == tgl_str) & 
                                (df_bk['Status'] == 'Selesai')
                            ]
                    except: pass

                    # --- C. HITUNG METRICS ---
                    total_masuk = df_masuk_today['Nominal'].sum() if not df_masuk_today.empty else 0
                    total_keluar = df_keluar_today['Nominal'].sum() if not df_keluar_today.empty else 0
                    
                    total_cash = 0; count_cash = 0
                    total_qris = 0; count_qris = 0
                    
                    if not df_masuk_today.empty:
                        mask_cash = df_masuk_today['Keterangan'].str.contains("Tunai", case=False, na=False)
                        total_cash = df_masuk_today[mask_cash]['Nominal'].sum()
                        count_cash = len(df_masuk_today[mask_cash])
                        
                        mask_qris = df_masuk_today['Keterangan'].str.contains("QRIS", case=False, na=False)
                        total_qris = df_masuk_today[mask_qris]['Nominal'].sum()
                        count_qris = len(df_masuk_today[mask_qris])
                    
                    cash_bersih = total_cash - total_keluar

                    # --- D. TAMPILKAN KARTU ---
                    c1, c2, c3, c4 = st.columns(4)
                    with c1:
                        st.markdown("**💳 QRIS**")
                        st.markdown(f"#### Rp {total_qris:,}".replace(',', '.'))
                        st.caption(f"{count_qris} Transaksi")
                    with c2:
                        st.markdown("**💵 Cash in**")
                        st.markdown(f"#### Rp {total_cash:,}".replace(',', '.'))
                        st.caption(f"{count_cash} Transaksi")
                    with c3:
                        st.markdown("**💸 Cash Out**")
                        st.markdown(f"#### Rp {total_keluar:,}".replace(',', '.'))
                    with c4:
                        st.markdown("**💰 Net Cash**")
                        st.markdown(f"#### Rp {cash_bersih:,}".replace(',', '.'))
                    
                    st.write("---")

                    # --- E. TAMPILKAN TABEL ---
                    col_tabel1, col_tabel2 = st.columns(2)
                    
                    with col_tabel1:
                        st.subheader("📥 Pemasukan")
                        if not df_masuk_today.empty:
                            df_ti = df_masuk_today[['Item', 'Keterangan', 'Nominal']].copy()
                            df_ti['Keterangan'] = df_ti['Keterangan'].apply(lambda x: x[:30] + "..." if len(str(x))>30 else x)
                            df_ti.insert(0, 'No', range(1, len(df_ti) + 1))
                            df_ti['Nominal'] = df_ti['Nominal'].apply(lambda x: "{:,.0f}".format(x).replace(',', '.'))
                            st.dataframe(df_ti, hide_index=True, use_container_width=True)
                        else: st.info("Kosong")

                    with col_tabel2:
                        st.subheader("📤 Pengeluaran")
                        if not df_keluar_today.empty:
                            df_to = df_keluar_today[['Item', 'Keterangan', 'Nominal']].copy()
                            df_to.insert(0, 'No', range(1, len(df_to) + 1))
                            df_to['Nominal'] = df_to['Nominal'].apply(lambda x: "{:,.0f}".format(x).replace(',', '.'))
                            st.dataframe(df_to, hide_index=True, use_container_width=True)
                        else: st.info("Kosong")

                    # --- F. PERSIAPAN DATA WA ---
                    
                    # 1. Statistik Kapster
                    txt_kapster = ""
                    if not df_booking_today.empty:
                        stats_kap = df_booking_today['Kapster'].value_counts()
                        for k, v in stats_kap.items():
                            txt_kapster += f"✂️ {k}: {v} Kepala\n"
                    else: txt_kapster = "- Belum ada data cukur -"

                    # 2. Statistik Menu
                    txt_layanan = ""
                    if not df_booking_today.empty:
                        stats_lay = df_booking_today['Layanan'].value_counts()
                        for k, v in stats_lay.items():
                            txt_layanan += f"💈 {k}: {v}\n"
                    else: txt_layanan = "-"

                    # 3. Statistik Pembayaran
                    txt_bayar = f"💵 Tunai: {count_cash} Trx\n💳 QRIS: {count_qris} Trx"

                    # 4. Statistik Pengeluaran (RINCIAN BARU)
                    txt_rincian_keluar = ""
                    if not df_keluar_today.empty:
                        for _, row in df_keluar_today.iterrows():
                            # Format angka
                            nom_fmt = "{:,.0f}".format(row['Nominal']).replace(',', '.')
                            # Batasi panjang nama item agar WA rapi
                            nm_item = row['Item']
                            if len(nm_item) > 20: nm_item = nm_item[:17] + "..."
                            
                            txt_rincian_keluar += f"   • {nm_item}: Rp {nom_fmt}\n"
                    else:
                        txt_rincian_keluar = "   - Nihil -"

                    # --- G. GENERATE WA ---
                    pesan_laporan = (
                        f"*LAPORAN HARIAN TRIPL3 BARBERSHOP*\n"
                        f"📅 Tanggal: {tanggal_indo(tgl_laporan)}\n"
                        f"------------------------------\n"
                        f"*📊 STATISTIK OPERASIONAL*\n\n"
                        f"*1. Performa Kapster:*\n{txt_kapster}\n"
                        f"*2. Menu Terjual:*\n{txt_layanan}\n"
                        f"*3. Jenis Transaksi:*\n{txt_bayar}\n\n"
                        f"*4. Rincian Pengeluaran:*\n{txt_rincian_keluar}\n"
                        f"------------------------------\n"
                        f"*💰 RINGKASAN KEUANGAN*\n\n"
                        f"Total Cash In : Rp {total_cash:,}".replace(',', '.') + "\n"
                        f"Total QRIS    : Rp {total_qris:,}".replace(',', '.') + "\n"
                        f"Total Omzet   : *Rp {total_masuk:,}*".replace(',', '.') + "\n"
                        f"\n"
                        f"Total Keluar  : Rp {total_keluar:,}".replace(',', '.') + "\n"
                        f"------------------------------\n"
                        f"💎 *SETORAN CASH (NET): Rp {cash_bersih:,}*".replace(',', '.') + "\n"
                        f"------------------------------\n"
                        f"🤖 *System Generated*"
                    )
                    
                    st.write("---")
                    st.success("Laporan Siap!")
                    link_lapor = f"https://wa.me/?text={urllib.parse.quote(pesan_laporan)}"
                    st.link_button("📤 Kirim Laporan Lengkap ke WA", link_lapor, type="primary")

                except Exception as e:
                    st.error(f"Gagal hitung rekap: {e}")      

        # --- TAB 5: LAPORAN MINGGUAN (FINAL FIX: UPGRADE MERGE, ADD-ON SEPARATE) ---
        with tab5:
            st.header("🏆 Laporan Prestasi Mingguan")
            
            # 1. Pilih Tanggal
            tgl_pilih = st.date_input("Pilih Tanggal dalam Minggu yang diinginkan", datetime.now())
            
            # Hitung Senin - Minggu
            start_week = tgl_pilih - timedelta(days=tgl_pilih.weekday())
            end_week = start_week + timedelta(days=6)
            
            st.info(f"📅 Periode Laporan: **{tanggal_indo(start_week)}** s/d **{tanggal_indo(end_week)}**")
            
            if st.button("Analisis Prestasi Kapster"):
                try:
                    # A. AMBIL DATA
                    sheet_in = get_google_sheet('Pemasukan')
                    df_in = pd.DataFrame(sheet_in.get_all_records())

                    if not df_in.empty:
                        # Filter & Clean
                        df_in['Tanggal'] = pd.to_datetime(df_in['Tanggal']).dt.date
                        df_in = df_in[(df_in['Tanggal'] >= start_week) & (df_in['Tanggal'] <= end_week)]
                        
                        def clean_duit(x):
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        df_in['Nominal'] = df_in['Nominal'].apply(clean_duit)

                        # B. PROSES DATA
                        kapsters = list(INFO_KAPSTER.keys())
                        total_gross = 0; total_disc = 0; total_net = 0; total_kepala = 0
                        laporan = {}

                        for k in kapsters:
                            # Filter baris milik kapster ini (dari keterangan)
                            df_k = df_in[df_in['Keterangan'].str.contains(f"- {k}", case=False, na=False)].copy()
                            
                            if df_k.empty:
                                laporan[k] = {'kepala':0, 'gross':0, 'disc':0, 'net':0, 'details':[]}
                                continue

                            # --- LOGIKA ITEM PINTAR ---
                            # 1. Grouping per Nota ID dulu
                            df_k['Nota_ID'] = df_k['Keterangan'].str.extract(r'\[(\w+)\]')
                            grouped = df_k.groupby('Nota_ID')
                            
                            stats_menu = {} # {NamaMenu: {'qty':0, 'gross':0}}
                            
                            k_gross = 0; k_disc = 0; k_net = 0
                            count_kepala = 0

                            for nota, group in grouped:
                                count_kepala += 1
                                
                                # Pisahkan Item Jasa (Positif) dan Diskon (Negatif)
                                items_pos = group[group['Nominal'] > 0].to_dict('records')
                                items_neg = group[group['Nominal'] < 0]['Nominal'].sum() # Total Diskon Nota ini
                                
                                # --- ALGORITMA MERGE UPGRADE ---
                                # 1. Cari Total Uang Upgrade di nota ini
                                total_biaya_upgrade = sum([x['Nominal'] for x in items_pos if "biaya upgrade" in str(x['Item']).lower()])
                                
                                # 2. Cari Item Utama (Target Merge) -> Yg ada tulisan "Up from"
                                target_idx = -1
                                for i, item in enumerate(items_pos):
                                    if "up from" in str(item['Item']).lower():
                                        target_idx = i
                                        break
                                
                                # 3. Proses List Item Akhir
                                final_items_nota = []
                                
                                if target_idx != -1 and total_biaya_upgrade > 0:
                                    # KETEMU PASANGANNYA: Merge Biaya Upgrade ke Item Utama
                                    for i, item in enumerate(items_pos):
                                        nama_lower = str(item['Item']).lower()
                                        
                                        if i == target_idx:
                                            # Ini Item Utama: Tambahkan uang upgrade, Bersihkan Nama
                                            new_nominal = item['Nominal'] + total_biaya_upgrade
                                            new_name = item['Item'].split(' (Up from')[0].strip() # Buang "(Up from...)"
                                            final_items_nota.append({'Item': new_name, 'Nominal': new_nominal})
                                        
                                        elif "biaya upgrade" in nama_lower:
                                            # Ini Item Biaya Upgrade: SKIP (Sudah dipindah uangnya)
                                            continue 
                                        
                                        else:
                                            # Ini Add-on / Item Lain: Masukkan apa adanya
                                            final_items_nota.append({'Item': item['Item'], 'Nominal': item['Nominal']})
                                else:
                                    # TIDAK ADA MERGE (Normal): Masukkan semua kecuali Biaya Upgrade yg stand alone (jarang)
                                    for item in items_pos:
                                        final_items_nota.append({'Item': item['Item'], 'Nominal': item['Nominal']})

                                # --- CATAT KE STATISTIK ---
                                # Loop item yang sudah rapi (Add-on terpisah, Upgrade tergabung)
                                nota_gross = 0
                                for f_item in final_items_nota:
                                    nm = f_item['Item']
                                    nom = f_item['Nominal']
                                    nota_gross += nom
                                    
                                    if nm not in stats_menu: stats_menu[nm] = {'qty': 0, 'gross': 0}
                                    stats_menu[nm]['qty'] += 1
                                    stats_menu[nm]['gross'] += nom
                                
                                # Hitung total uang nota
                                k_gross += nota_gross
                                k_disc += abs(items_neg)
                                k_net += (nota_gross - abs(items_neg))

                            # --- END LOOP NOTA ---
                            
                            # Siapkan Data Tabel
                            detail_list = []
                            for m, stat in stats_menu.items():
                                detail_list.append({'Menu': m, 'Qty': stat['qty'], 'Total Gross': stat['gross']})
                            
                            # Masukkan Baris Diskon Total (Jika ada)
                            if k_disc > 0:
                                # Hitung frekuensi diskon
                                count_trx_disc = df_k[df_k['Nominal'] < 0].shape[0]
                                detail_list.append({'Menu': '🔻 Potongan Diskon', 'Qty': count_trx_disc, 'Total Gross': -k_disc})

                            laporan[k] = {
                                'kepala': count_kepala, 'gross': k_gross, 'disc': k_disc, 'net': k_net, 'details': detail_list
                            }
                            total_gross += k_gross; total_disc += k_disc; total_net += k_net; total_kepala += count_kepala

                        # --- TAMPILAN UI ---
                        st.write("---")
                        st.markdown("""<style>[data-testid="stMetricValue"] { font-size: 20px !important; word-wrap: break-word !important; }</style>""", unsafe_allow_html=True)

                        st.markdown("### 🏢 Performa Total Toko")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Total Kepala", f"{total_kepala}")
                        c2.metric("Total Gross", f"Rp {total_gross:,}".replace(',', '.'))
                        c3.metric("Total Diskon", f"Rp {total_disc:,}".replace(',', '.'), delta_color="inverse")
                        c4.metric("Total Net", f"Rp {total_net:,}".replace(',', '.'))
                        st.write("---")

                        # Per Kapster
                        col_k1, col_k2 = st.columns(2)
                        for i, k in enumerate(kapsters):
                            d = laporan[k]
                            with (col_k1 if i % 2 == 0 else col_k2):
                                st.markdown(f"### 💈 {k}")
                                st.image(INFO_KAPSTER[k]['img'], width=100)
                                m1, m2 = st.columns([1, 2])
                                m1.metric("✂️ Kepala", f"{d['kepala']}")
                                m2.metric("💰 Net", f"Rp {d['net']:,}".replace(',', '.'))
                                
                                if d['details']:
                                    df_d = pd.DataFrame(d['details'])
                                    # Sort: Diskon paling bawah, Sisanya by Qty
                                    df_d['Order'] = df_d['Menu'].apply(lambda x: 1 if 'Diskon' in x else 0)
                                    df_d = df_d.sort_values(by=['Order', 'Qty'], ascending=[True, False]).drop(columns=['Order'])
                                    
                                    # Total Row
                                    row_tot = pd.DataFrame([{'Menu': '⚡ TOTAL NET', 'Qty': d['kepala'], 'Total Gross': d['net']}])
                                    df_show = pd.concat([df_d, row_tot], ignore_index=True)
                                    
                                    df_show['Total Gross'] = df_show['Total Gross'].apply(lambda x: f"{int(x):,}".replace(',', '.'))
                                    st.caption("Rincian Layanan & Add-on:")
                                    st.dataframe(df_show, hide_index=True, use_container_width=True)
                                else: st.info("Belum ada data.")
                                st.write("---")
                        
                        # Grafik
                        st.subheader("📊 Grafik")
                        chart_df = pd.DataFrame({'Kapster': kapsters, 'Jumlah Kepala': [laporan[k]['kepala'] for k in kapsters]})
                        st.altair_chart(alt.Chart(chart_df).mark_bar().encode(x='Kapster', y='Jumlah Kepala'), use_container_width=True)

                        # WA
                        header_wa = f"*RAPOR MINGGUAN TRIPL3 BARBERSHOP*\nPeriode: {tanggal_indo(start_week)} - {tanggal_indo(end_week)}\n==============================\n"
                        body_wa = ""
                        for k in kapsters:
                            d = laporan[k]
                            body_wa += f"💈 *{k}*: {d['kepala']} Kepala | Net: Rp {d['net']:,}\n".replace(',', '.')
                            if d['disc'] > 0: body_wa += f"   (Disc: Rp {d['disc']:,})\n".replace(',', '.')
                            body_wa += "----------------\n"
                        
                        footer_wa = f"🏢 *TOTAL*: Rp {total_net:,}".replace(',', '.')
                        st.link_button("📤 Kirim WA", f"https://wa.me/?text={urllib.parse.quote(header_wa+body_wa+footer_wa)}", type="primary")

                    else: st.warning("Data Pemasukan Kosong.")
                except Exception as e: st.error(f"Error: {e}")

        # --- TAB 6: JUAL POMADE (FLEXIBEL: KAMERA / GALERI) ---
        with tab6:
            st.header("📸 Penjualan Produk")
            
            col_input, col_rekap = st.columns([1, 1])
            
            with col_input:
                st.subheader("Input Penjualan")
                
                # Kita gunakan form tanpa clear_on_submit dulu agar file tidak hilang saat proses
                with st.form("form_pomade", clear_on_submit=True):
                    nama_p = st.text_input("Nama Produk / Pomade", placeholder="Blue Water Based" )
                    harga_p = st.number_input("Nominal (Rp)", min_value=0, step=1000)
                    ket_p = st.text_area("Keterangan", placeholder="neto, tipe, dll")
                    
                    st.write("---")
                    st.caption("Foto Barang Terjual (Wajib)")
                    
                    # --- PERUBAHAN DI SINI (GANTI JADI FILE UPLOADER) ---
                    # User bisa pilih: Kamera atau Galeri
                    gambar_pomade = st.file_uploader("Upload Foto", type=['jpg', 'png', 'jpeg'])
                    
                    submit_pomade = st.form_submit_button("Simpan Transaksi & Upload", type="primary")
                    
                    if submit_pomade:
                        # Validasi Input Lengkap
                        if not nama_p or harga_p <= 0:
                            st.warning("⚠️ Mohon isi Nama Produk dan Nominal.")
                        elif not gambar_pomade:
                            st.error("⚠️ WAJIB UPLOAD FOTO BUKTI DULU!")
                        else:
                            with st.spinner("Sedang mengupload foto ke Drive & Simpan Data..."):
                                # 1. Buat Nama File Unik
                                waktu_file = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")
                                
                                # Kita ambil ekstensi file aslinya (jpg/png)
                                ext = gambar_pomade.name.split('.')[-1]
                                nama_file_foto = f"POMADE_{nama_p}_{waktu_file}.{ext}"
                                
                                # 2. Upload ke Drive
                                link_hasil = upload_ke_drive(gambar_pomade, nama_file_foto)
                                
                                if link_hasil:
                                    # 3. Simpan Data ke Excel
                                    sukses = simpan_transaksi_pomade(nama_p, int(harga_p), ket_p, link_hasil)
                                    
                                    if sukses:
                                        st.success(f"✅ Berhasil! {nama_p} terjual.")
                                        time.sleep(1)
                                        st.rerun()
                                else:
                                    st.error("Gagal mengupload foto. Cek koneksi atau izin Drive.")
    
            with col_rekap:
                st.subheader("📊 Rekap Harian Pomade")
                if st.button("🔄 Refresh Data"): st.rerun()
                
                df_pomade = get_rekap_pomade_harian()
                
                if not df_pomade.empty:
                    total_omzet = df_pomade['Nominal'].sum()
                    st.metric("Total Hari Ini", f"Rp {total_omzet:,}")
                    
                    # Tampilkan Tabel
                    st.dataframe(
                        df_pomade, 
                        hide_index=True,
                        use_container_width=True
                    )
                else:
                    st.info("Belum ada penjualan hari ini.")
                
    elif password: st.error("Salah!")

# ==========================================
# 3. HALAMAN OWNER INSIGHT
# ==========================================
elif menu == "Owner Insight":
    st.title("📈 Owner Insight")
    
    pass_owner = st.sidebar.text_input("Password Owner", type="password")
    
    if pass_owner == "BERKAT2026":
        st.sidebar.success("Akses Diterima ✅")
        
        # --- A. CONTROL PANEL (FITUR KUNCI DISKON) ---
        with st.container(border=True):
            st.subheader("🎛️ Control Panel Toko")
            c_ctrl1, c_ctrl2 = st.columns([1, 3])
            
            curr_status = get_diskon_status()
            is_unlocked = (curr_status == 'UNLOCKED')
            
            with c_ctrl1:
                # Tombol Switch
                mode_diskon = st.toggle("Buka Akses Diskon?", value=is_unlocked)
            
            with c_ctrl2:
                # Logika Update Database
                new_status = 'UNLOCKED' if mode_diskon else 'LOCKED'
                if new_status != curr_status:
                    with st.spinner("Mengupdate sistem kasir..."):
                        set_diskon_status(new_status)
                    st.rerun()
                
                if mode_diskon:
                    st.success("✅ Status: Kasir BISA memberi diskon.")
                else:
                    st.error("🔒 Status: Fitur Diskon Kasir TERKUNCI/HILANG.")
        # ---------------------------------------------
        
        DATA_LAYANAN = get_daftar_layanan() 
        tab_insight, tab_expense, tab_profit = st.tabs(["📅 Performa Bulanan", "💸 Input Pengeluaran", "💵 Profit & Share"])
               
        # --- TAB 1: PERFORMA BULANAN (FINAL UPDATE: SHOW GROSS & DISCOUNT PER KAPSTER) ---
        with tab_insight:
            st.header("Analisis Bulanan")
            
            col_bln1, col_bln2 = st.columns(2)
            with col_bln1:
                bulan_pilih = st.selectbox("Pilih Bulan", range(1, 13), index=datetime.now().month - 1, key="pilih_bln_1")
            with col_bln2:
                tahun_pilih = st.number_input("Pilih Tahun", min_value=2024, max_value=2030, value=datetime.now().year, key="pilih_thn_1")
            
            if st.button("Tampilkan Data", key="btn_show_1"):
                try:
                    # --- A. AMBIL DATA BOOKING (Mapping Kepala) ---
                    sheet_booking = get_google_sheet('Booking')
                    data_bk = sheet_booking.get_all_records()
                    df_bk = pd.DataFrame(data_bk)
                    
                    # --- B. AMBIL DATA PEMASUKAN (Sumber Uang) ---
                    sheet_uang = get_google_sheet('Pemasukan')
                    data_uang = sheet_uang.get_all_records()
                    df_in = pd.DataFrame(data_uang)

                    if not df_in.empty:
                        # 1. Filter Tanggal Pemasukan
                        df_in['Tanggal'] = pd.to_datetime(df_in['Tanggal'])
                        df_in = df_in[
                            (df_in['Tanggal'].dt.month == bulan_pilih) & 
                            (df_in['Tanggal'].dt.year == tahun_pilih)
                        ]
                        
                        # 2. Bersihkan Nominal
                        def clean_duit(x):
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        df_in['Nominal'] = df_in['Nominal'].apply(clean_duit)

                        # --- C. PROSES AGREGASI (LOGIKA LEDGER) ---
                        kapsters = list(INFO_KAPSTER.keys())
                        laporan = {}
                        
                        total_gross_toko = 0
                        total_diskon_toko = 0
                        total_net_toko = 0
                        total_kepala_toko = 0
                        
                        all_shop_items = [] # Global stats

                        for k in kapsters:
                            # 1. Hitung Kepala (Booking)
                            jumlah_kepala = 0
                            if not df_bk.empty:
                                try:
                                    df_bk['Tanggal'] = pd.to_datetime(df_bk['Tanggal'])
                                    df_bk_k = df_bk[
                                        (df_bk['Kapster'] == k) & 
                                        (df_bk['Status'] == 'Selesai') &
                                        (df_bk['Tanggal'].dt.month == bulan_pilih) &
                                        (df_bk['Tanggal'].dt.year == tahun_pilih)
                                    ]
                                    jumlah_kepala = len(df_bk_k)
                                except: pass

                            # 2. Filter Pemasukan Kapster
                            df_k = df_in[df_in['Keterangan'].str.contains(f"- {k}", case=False, na=False)].copy()
                            
                            if df_k.empty:
                                laporan[k] = {'kepala': jumlah_kepala, 'gross': 0, 'disc': 0, 'net': 0, 'details': []}
                                total_kepala_toko += jumlah_kepala
                                continue

                            # 3. Smart Merge per Nota
                            df_k['Nota_ID'] = df_k['Keterangan'].str.extract(r'\[(\w+)\]')
                            grouped = df_k.groupby('Nota_ID')
                            
                            stats_menu = {}
                            k_gross = 0; k_disc = 0; k_net = 0

                            for nota, group in grouped:
                                items_pos = group[group['Nominal'] > 0].to_dict('records')
                                items_neg = group[group['Nominal'] < 0]['Nominal'].sum() # Diskon (Negatif)
                                
                                # Deteksi & Gabung Upgrade
                                total_biaya_upgrade = sum([x['Nominal'] for x in items_pos if "biaya upgrade" in str(x['Item']).lower()])
                                target_idx = -1
                                for i, item in enumerate(items_pos):
                                    if "up from" in str(item['Item']).lower():
                                        target_idx = i; break
                                
                                final_items_nota = []
                                if target_idx != -1 and total_biaya_upgrade > 0:
                                    for i, item in enumerate(items_pos):
                                        if i == target_idx:
                                            new_nom = item['Nominal'] + total_biaya_upgrade
                                            new_name = item['Item'].split(' (Up from')[0].strip()
                                            final_items_nota.append({'Item': new_name, 'Nominal': new_nom})
                                        elif "biaya upgrade" in str(item['Item']).lower(): continue
                                        else: final_items_nota.append({'Item': item['Item'], 'Nominal': item['Nominal']})
                                else:
                                    for item in items_pos: final_items_nota.append({'Item': item['Item'], 'Nominal': item['Nominal']})

                                # Hitung Uang
                                nota_gross = 0
                                for f_item in final_items_nota:
                                    nm = f_item['Item']
                                    nom = f_item['Nominal']
                                    nota_gross += nom
                                    
                                    if nm not in stats_menu: stats_menu[nm] = {'qty': 0, 'gross': 0}
                                    stats_menu[nm]['qty'] += 1
                                    stats_menu[nm]['gross'] += nom
                                    all_shop_items.append({'Menu': nm, 'Qty': 1, 'Total Gross': nom})
                                
                                k_gross += nota_gross
                                k_disc += abs(items_neg)
                                k_net += (nota_gross - abs(items_neg))

                            # Detail List for Table
                            detail_list = []
                            for m, stat in stats_menu.items():
                                detail_list.append({'Menu': m, 'Qty': stat['qty'], 'Total Gross': stat['gross']})
                            
                            laporan[k] = {
                                'kepala': jumlah_kepala, 'gross': k_gross, 'disc': k_disc, 'net': k_net, 'details': detail_list
                            }
                            total_kepala_toko += jumlah_kepala
                            total_gross_toko += k_gross
                            total_diskon_toko += k_disc
                            total_net_toko += k_net

                        # --- LOGIKA TOP KAPSTER ---
                        klasemen = []
                        for nama, stats in laporan.items():
                            klasemen.append({'nama': nama, 'kepala': stats['kepala'], 'omzet': stats['net']})
                        klasemen.sort(key=lambda x: (x['kepala'], x['omzet']), reverse=True)
                        top_kapster_toko = klasemen[0]['nama'] if klasemen else "-"

                        # --- UI DISPLAY ---
                        st.divider()
                        st.markdown("""<style>[data-testid="stMetricValue"] { font-size: 20px !important; word-wrap: break-word !important; }</style>""", unsafe_allow_html=True)

                        # 1. TOTAL TOKO
                        st.markdown("### 🏢 Performa Total Toko (Bulanan)")
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Total Kepala", f"{total_kepala_toko} Orang")
                        k2.metric("Total Gross (Kotor)", f"Rp {total_gross_toko:,}".replace(',', '.'))
                        k3.metric("Total Diskon", f"Rp {total_diskon_toko:,}".replace(',', '.'), delta_color="inverse")
                        k4.metric("Total Net (Bersih)", f"Rp {total_net_toko:,}".replace(',', '.'))
                        
                        # 2. MENU TERLARIS
                        if all_shop_items:
                            df_shop_items = pd.DataFrame(all_shop_items)
                            best_seller = df_shop_items.groupby('Menu').agg({'Qty': 'sum', 'Total Gross': 'sum'}).reset_index()
                            best_seller = best_seller.sort_values(by=['Qty', 'Total Gross'], ascending=False)
                            best_seller['Total Omset'] = best_seller['Total Gross'].apply(lambda x: f"Rp {x:,}".replace(',', '.'))
                            
                            with st.expander("📊 Lihat Menu Terlaris & Omset", expanded=False):
                                st.dataframe(best_seller[['Menu', 'Qty', 'Total Omset']], hide_index=True, use_container_width=True)
                        else: st.info("Belum ada data penjualan.")

                        st.write("---")

                        # 3. RINCIAN PER KAPSTER
                        c1, c2 = st.columns(2)
                        for i, k in enumerate(kapsters):
                            data_k = laporan[k]
                            with (c1 if i % 2 == 0 else c2):
                                st.markdown(f"### 💈 {k}")
                                m1, m2 = st.columns([1, 2])
                                m1.metric("✂️ Kepala", f"{data_k['kepala']}")
                                m2.metric("💰 Net (Masuk)", f"Rp {data_k['net']:,}".replace(',', '.'))
                                
                                # --- TAMBAHAN INFO GROSS & DISKON PER KAPSTER ---
                                st.markdown(f"""
                                <div style="display: flex; justify-content: space-between; font-size: 14px; margin-bottom: 5px;">
                                    <span>💵 Gross: <b>Rp {data_k['gross']:,}</b></span>
                                    <span style="color: #ff4b4b;">🔻 Disc: <b>- Rp {data_k['disc']:,}</b></span>
                                </div>
                                """.replace(',', '.'), unsafe_allow_html=True)
                                # ------------------------------------------------

                                if data_k['details']:
                                    df_det = pd.DataFrame(data_k['details'])
                                    df_det = df_det.sort_values(by='Qty', ascending=False)
                                    df_det['Total Gross'] = df_det['Total Gross'].apply(lambda x: f"{x:,}".replace(',', '.'))
                                    st.dataframe(df_det[['Menu', 'Qty', 'Total Gross']], hide_index=True, use_container_width=True)
                                else: st.info("Belum ada data.")
                                st.write("---")
                        
                        # 4. GRAFIK
                        chart_data = pd.DataFrame({'Kapster': kapsters, 'Jumlah Kepala': [laporan[k]['kepala'] for k in kapsters]})
                        custom_chart = alt.Chart(chart_data).mark_bar().encode(
                            x=alt.X('Kapster', axis=alt.Axis(labelAngle=0, title="Nama Kapster")),
                            y=alt.Y('Jumlah Kepala', axis=alt.Axis(tickMinStep=1)),
                            tooltip=['Kapster', 'Jumlah Kepala']
                        ).properties(title="Grafik Performa Bulanan")
                        st.altair_chart(custom_chart, use_container_width=True)

                    else: st.warning("Belum ada data di bulan ini.")
                except Exception as e: st.error(f"Error: {e}")

        # --- TAB 2: INPUT PENGELUARAN OWNER (SOLUSI: CALLBACK RESET) ---
        with tab_expense:
            st.header("💰 Input Pengeluaran Owner")
            st.caption("Gunakan ini untuk mencatat pengeluaran besar (Gaji, Sewa, Maintenance).")
            
            # 1. Definisi Data & Fungsi Reset (Harus di paling atas tab ini)
            list_rekomendasi = ["Gaji Kapster", "Sewa Ruko", "Belanja Logistik Bulanan", "Maintenance Alat"]
            
            # Fungsi Callback: Dijalankan SEBELUM halaman reload
            def reset_form_pengeluaran():
                st.session_state['own_select'] = list_rekomendasi[0] # Reset ke pilihan pertama
                st.session_state['own_text'] = ""
                st.session_state['own_nom'] = 0
                st.session_state['own_ket'] = ""
            
            # 2. Inisialisasi Session State (Agar tidak error saat pertama buka)
            if 'own_select' not in st.session_state: st.session_state['own_select'] = list_rekomendasi[0]
            if 'own_text' not in st.session_state: st.session_state['own_text'] = ""
            if 'own_nom' not in st.session_state: st.session_state['own_nom'] = 0
            if 'own_ket' not in st.session_state: st.session_state['own_ket'] = ""

            # 3. Widget Input
            pilih_nama = st.selectbox("Nama Pengeluaran", list_rekomendasi + ["📝 Input Baru..."], key="own_select")
            
            # Logika Text Input: Muncul hanya jika pilih 'Input Baru', tapi valuenya diikat session_state
            nama_final = pilih_nama
            if pilih_nama == "📝 Input Baru...":
                nama_final = st.text_input("Ketik Nama Pengeluaran", key="own_text")
            
            nominal = st.number_input("Nominal (Rp)", min_value=0, step=10000, key="own_nom")
            ket_bebas = st.text_input("Keterangan", key="own_ket")
            
            # 4. Tombol Eksekusi
            if st.button("Simpan & Buat Pemberitahuan", type="primary"):
                # Validasi: Jika input baru dipilih, pastikan teks tidak kosong
                if pilih_nama == "📝 Input Baru..." and not st.session_state['own_text']:
                    st.warning("Mohon ketik nama pengeluaran baru.")
                elif nominal <= 0:
                    st.warning("Nominal harus lebih dari 0.")
                else:
                    ket_final = f"[BY OWNER] {ket_bebas}"
                    
                    # Simpan ke Database
                    if simpan_pengeluaran(nama_final, ket_final, nominal):
                        st.success("✅ Data Berhasil Disimpan ke Database!")
                        
                        # Generate Pesan WA
                        tgl_now = (datetime.utcnow() + timedelta(hours=7)).strftime("%d-%m-%Y %H:%M")
                        val_fmt = f"{int(nominal):,}".replace(',', '.')
                        
                        pesan_wa = (
                            f"*INPUT PENGELUARAN OWNER*\n"
                            f"📅 Waktu: {tgl_now}\n"
                            f"--------------------------------\n"
                            f"📝 Item: *{nama_final}*\n"
                            f"💸 Nominal: *Rp {val_fmt}*\n"
                            f"ℹ️ Ket: {ket_bebas}\n"
                            f"--------------------------------\n"
                            f"✅ *Tercatat di Sistem*"
                        )
                        
                        # Tampilkan Tombol WA
                        link_wa = f"https://wa.me/?text={urllib.parse.quote(pesan_wa)}"
                        st.link_button("📤 Kirim Bukti ke WA Grup", link_wa)
                        
                        st.divider()
                        st.info("Data tersimpan. Tekan tombol di bawah untuk input data baru.")
                    else:
                        st.error("Gagal menyimpan ke database.")

            # 5. Tombol Reset (Menggunakan on_click Callback)
            # Ini kuncinya: on_click akan menjalankan fungsi reset_form_pengeluaran DULUAN, baru reload halaman.
            st.button("🔄 Input Lagi / Bersihkan Form", on_click=reset_form_pengeluaran)

        # --- TAB 3: PROFIT & SHARE ---
        with tab_profit:
            st.header("💵 Profit & Share Calculator")
            st.caption("Perhitungan Laba Bersih (Omset Jasa - Biaya Operasional). Pomade tidak termasuk.")

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                bln_profit = st.selectbox("Bulan", range(1, 13), index=datetime.now().month - 1, key="prof_bln")
            with col_p2:
                thn_profit = st.number_input("Tahun", min_value=2024, max_value=2030, value=datetime.now().year, key="prof_thn")

            if st.button("Hitung Profit Sharing", type="primary"):
                try:
                    # 1. HITUNG OMSET & DISKON
                    total_revenue = 0
                    total_discount = 0
                    
                    sheet_booking = get_google_sheet('Booking')
                    data_bk = sheet_booking.get_all_records()
                    df_bk = pd.DataFrame(data_bk)
                    
                    if not df_bk.empty and 'Status' in df_bk.columns:
                        df_bk = df_bk[df_bk['Status'] == 'Selesai']
                        df_bk['Tanggal'] = pd.to_datetime(df_bk['Tanggal'])
                        df_rev = df_bk[
                            (df_bk['Tanggal'].dt.month == bln_profit) & 
                            (df_bk['Tanggal'].dt.year == thn_profit)
                        ]
                        
                        if not df_rev.empty:
                            def clean_val(x):
                                try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                                except: return 0

                            # Hitung Revenue (Harga Final)
                            if 'Harga_Final' in df_rev.columns:
                                df_rev['Harga_Final'] = df_rev['Harga_Final'].apply(clean_val)
                                total_revenue = df_rev['Harga_Final'].sum()
                                if total_revenue == 0: # Fallback
                                    for _, row in df_rev.iterrows():
                                        nama_lay = str(row['Layanan']).strip()
                                        for db_n, db_v in DATA_LAYANAN.items():
                                            if str(db_n).strip() == nama_lay:
                                                total_revenue += db_v.get('Harga', 0); break
                            else: # Fallback total
                                for _, row in df_rev.iterrows():
                                    nama_lay = str(row['Layanan']).strip()
                                    for db_n, db_v in DATA_LAYANAN.items():
                                        if str(db_n).strip() == nama_lay:
                                            total_revenue += db_v.get('Harga', 0); break

                            # Hitung Diskon
                            if 'Diskon' in df_rev.columns:
                                df_rev['Diskon'] = df_rev['Diskon'].apply(clean_val)
                                total_discount = df_rev['Diskon'].sum()
                    
                    # 2. HITUNG PENGELUARAN
                    total_expense = 0
                    rincian_biaya = []
                    
                    sheet_out = get_google_sheet('Pengeluaran')
                    data_out = sheet_out.get_all_records()
                    df_out = pd.DataFrame(data_out)
                    
                    if not df_out.empty:
                        df_out['Tanggal'] = pd.to_datetime(df_out['Tanggal'])
                        df_exp = df_out[
                            (df_out['Tanggal'].dt.month == bln_profit) & 
                            (df_out['Tanggal'].dt.year == thn_profit)
                        ]
                        if not df_exp.empty:
                            total_expense = df_exp['Nominal'].sum()
                            rincian_biaya = df_exp[['Item', 'Nominal', 'Keterangan']].to_dict('records')

                    # 3. HITUNG HASIL AKHIR
                    net_profit = total_revenue - total_expense
                    share_42 = net_profit * 0.42
                    share_05 = net_profit * 0.05
                    share_53 = net_profit * 0.53

                    # TAMPILAN
                    st.divider()
                    
                    st.subheader("1. Pemasukan (Omset Jasa)")
                    c_rev1, c_rev2 = st.columns([2, 1])
                    with c_rev1:
                        st.markdown(f"### 💰 Rp {total_revenue:,}".replace(',', '.'))
                        st.caption("Total Uang Masuk (Net)")
                    with c_rev2:
                        if total_discount > 0:
                            st.metric("Total Diskon", f"Rp {total_discount:,}".replace(',', '.'), delta="- pengurang", delta_color="inverse")
                        else: st.metric("Total Diskon", "Rp 0")
                    
                    st.write("---")
                    st.subheader("2. Pengeluaran (Biaya)")
                    st.markdown(f"### 💸 Rp {total_expense:,}".replace(',', '.'))
                    
                    with st.expander("Lihat Rincian Biaya"):
                        if rincian_biaya:
                            for idx, item in enumerate(rincian_biaya):
                                hrg = f"Rp {item['Nominal']:,}".replace(',', '.')
                                st.write(f"{idx+1}. **{item['Item']}** ({hrg}) - {item['Keterangan']}")
                        else: st.info("Tidak ada pengeluaran bulan ini.")
                    
                    st.write("---")
                    st.subheader("3. Laba Bersih (Net Profit)")
                    st.latex(r'''\text{Net Profit} = \text{Omset Jasa} - \text{Total Biaya}''')
                    
                    if net_profit >= 0:
                        st.success(f"# 💎 Rp {net_profit:,}".replace(',', '.'))
                    else:
                        st.error(f"# 🔻 Rp {net_profit:,} (Rugi)".replace(',', '.'))
                    
                    st.write("---")
                    st.subheader("4. Pembagian Profit (Share)")
                    
                    c_s1, c_s2, c_s3 = st.columns(3)
                    with c_s1:
                        st.info("**Share 42%**")
                        st.markdown(f"#### Rp {int(share_42):,}".replace(',', '.'))
                    with c_s2:
                        st.warning("**Share 5%**")
                        st.markdown(f"#### Rp {int(share_05):,}".replace(',', '.'))
                    with c_s3:
                        st.success("**Share 53%**")
                        st.markdown(f"#### Rp {int(share_53):,}".replace(',', '.'))

                except Exception as e:
                    st.error(f"Gagal menghitung profit: {e}")

    elif pass_owner:
        st.error("Password Salah!")
































































