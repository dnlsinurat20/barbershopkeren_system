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
# Removed unused import: google.oauth2

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Barbershop Keren System", page_icon="💈", layout="wide")

# --- BARBER PROFILE DATA ---
INFO_KAPSTER = {
    "Kenzo": {
        "deskripsi": "Master of Classic Cuts. Spesialis Pompadour, Executive Contour, dan Signature Hot Towel Shave.",
        "img": "Kenzo.jpeg" 
    },
    "Arka": {
        "deskripsi": "Creative Barber & Color Specialist. Ahli dalam Fashion Hair Color, Hair Tattoo/Grooming, dan Urban Modern Cut.",
        "img": "Arka.jpeg"
    }
}

# --- CSS: HIDE UPLOAD LIMIT TEXT ---
st.markdown("""
<style>
    [data-testid="stFileUploader"] section > div > small { display: none; }
</style>
""", unsafe_allow_html=True)

# --- SECURITY CONFIGURATION (LOAD FROM SECRETS) ---
# Local: Create .streamlit/secrets.toml file
# Cloud: Set in Streamlit Dashboard
try:
    FOLDER_ID_DRIVE = st.secrets["drive"]["folder_id"]
    SCRIPT_URL = st.secrets["drive"]["script_url"]
except:
    st.error("Secrets belum dikonfigurasi. Cek .streamlit/secrets.toml")
    st.stop()

# --- UPLOAD FUNCTION ---
def upload_ke_drive(file_buffer, nama_file_simpan):
    try:
        string_gambar = base64.b64encode(file_buffer.getvalue()).decode('utf-8')
        payload = {"filename": nama_file_simpan, "image": string_gambar}
        headers = {'Content-Type': 'application/json'}
        
        response = requests.post(SCRIPT_URL, data=json.dumps(payload), headers=headers)
        
        if response.status_code == 200:
            hasil = response.json()
            if hasil.get("result") == "success":
                return hasil.get("link") 
            else:
                st.error(f"Gagal dari Server: {hasil.get('message')}")
                return None
        else:
            st.error(f"Error HTTP: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error Koneksi Python: {e}")
        return None 
    
# --- HELPERS: NUMBER FORMATTING ---
def format_angka(nilai):
    return "{:,.0f}".format(nilai).replace(',', '.')
    
# --- HELPERS: DATE FORMATTING ---
def tanggal_indo(tgl_str):
    try:
        # Month names in Indonesian for UI
        bulan_indo = {
            1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 
            5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus", 
            9: "September", 10: "Oktober", 11: "November", 12: "Desember"
        }
        if isinstance(tgl_str, (date, datetime)): tgl_obj = tgl_str
        else: tgl_obj = datetime.strptime(str(tgl_str), "%Y-%m-%d")
        return f"{tgl_obj.day} {bulan_indo[tgl_obj.month]} {tgl_obj.year}"
    except: return tgl_str

# --- HELPERS: TIME CONVERSION ---
def str_to_menit(jam_str):
    try: h, m = map(int, jam_str.split(':')); return h * 60 + m
    except: return 0

def menit_to_str(total_menit):
    h = total_menit // 60; m = total_menit % 60; return f"{h:02}:{m:02}"

# --- HELPERS: PHONE NUMBER FORMATTING ---
def format_nomor_wa(nomor):
    nomor = str(nomor).strip()
    if nomor.startswith("0"): return "62" + nomor[1:]
    elif nomor.startswith("62"): return nomor
    else: return "62" + nomor 

def format_wa_0(nomor):
    nomor = str(nomor).strip().replace('-', '').replace(' ', '').replace('+', '').replace('.', '')
    if nomor.startswith('62'): return '0' + nomor[2:]
    elif nomor.startswith('8'): return '0' + nomor
    return nomor

# --- SETUP SESSION STATE ---
if 'nota_terakhir' not in st.session_state:
    st.session_state['nota_terakhir'] = None

# --- DATABASE CONNECTION FUNCTION (HYBRID AUTH) ---
@st.cache_resource
def get_google_sheet(sheet_name):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # PRIORITY 1: Check for Secrets (Cloud Production)
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        # PRIORITY 2: Check Local File (Local Development)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
            
        client = gspread.authorize(creds)
        return client.open('TRIPL3_Barbershop_DB').worksheet(sheet_name)
    except Exception as e:
        st.error(f"Koneksi Database Gagal: {e}")
        st.stop()

# --- GET SERVICE DATA FUNCTION ---
@st.cache_data(ttl=600)
def get_daftar_layanan():
    try:
        sheet = get_google_sheet('Layanan')
        data = sheet.get_all_records()
        layanan_dict = {}
        for item in data:
            nama = item['Nama_Layanan']
            durasi_raw = str(item['Durasi']).lower().replace('menit', '').replace('m', '').strip()
            try: durasi_int = int(durasi_raw)
            except: durasi_int = 45 
            
            layanan_dict[nama] = {
                'Harga': int(str(item['Harga']).replace('.','').replace(',','')), 
                'Durasi': durasi_int, 
                'Deskripsi': item['Deskripsi']
            }
        return layanan_dict
    except:
        return {"Triple A (Default)": {'Harga': 70000, 'Durasi': 45, 'Deskripsi': 'Standard'}}

# --- RECEIPT GENERATION FUNCTION ---
def generate_receipt_image(nama, list_items, total_normal, diskon_val, harga_final, kapster, tanggal, jam, no_nota):
    # Setup Canvas
    tinggi_base = 600
    tinggi_per_item = 40
    H = tinggi_base + (len(list_items) * tinggi_per_item)
    W = 400
    
    img = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(img)
    
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

    # HEADER LOGO
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
        text_bbox = draw.textbbox((0, 0), "BARBERSHOP KEREN", font=font_title)
        x_pos = (W - (text_bbox[2] - text_bbox[0])) / 2
        draw.text((x_pos, y), "BARBERSHOP KEREN", font=font_title, fill='black')
        y += 40

    # ADDRESS (Indonesian Context)
    def draw_centered(text, font, y_curr, color='black'):
        bbox = draw.textbbox((0, 0), text, font=font)
        w_text = bbox[2] - bbox[0]
        draw.text(((W - w_text) / 2, y_curr), text, font=font, fill=color)
        return y_curr + (bbox[3] - bbox[1]) + 5

    y = draw_centered("Jl. Merdeka No. 10", font_small, y) # Change to your address
    y = draw_centered("Jakarta Selatan", font_small, y)
    y += 5
    y = draw_centered("WA: 0812-XXXX-XXXX", font_small, y)
    
    y += 10
    draw.line((20, y, W-20, y), fill='black', width=2)
    y += 20

    # TRANSACTION INFO
    draw.text((30, y), f"No. Nota : {no_nota}", font=font_bold, fill='black'); y += 25
    draw.text((30, y), f"Tanggal  : {tanggal} {jam}", font=font_reg, fill='black'); y += 25
    draw.text((30, y), f"Kapster  : {kapster}", font=font_reg, fill='black'); y += 25
    draw.text((30, y), f"Customer : {nama}", font=font_reg, fill='black'); y += 30
    draw.line((20, y, W-20, y), fill='grey', width=1); y += 20

    # DETAILS
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
    
    # SUBTOTAL, DISCOUNT, TOTAL
    draw.text((30, y), "Subtotal", font=font_reg, fill='black')
    sub_fmt = f"Rp {total_normal:,}".replace(',', '.')
    sub_bbox = draw.textbbox((0,0), sub_fmt, font=font_reg)
    draw.text((W - 30 - (sub_bbox[2]-sub_bbox[0]), y), sub_fmt, font=font_reg, fill='black'); y += 25

    if diskon_val > 0:
        draw.text((30, y), "Diskon", font=font_reg, fill='red')
        disc_fmt = f"- Rp {diskon_val:,}".replace(',', '.')
        disc_bbox = draw.textbbox((0,0), disc_fmt, font=font_reg)
        draw.text((W - 30 - (disc_bbox[2]-disc_bbox[0]), y), disc_fmt, font=font_reg, fill='red'); y += 25

    draw.line((20, y, W-20, y), fill='black', width=2); y += 15

    draw.text((30, y), "TOTAL BAYAR", font=font_title, fill='black')
    total_fmt = f"Rp {harga_final:,}".replace(',', '.')
    total_bbox = draw.textbbox((0,0), total_fmt, font=font_title)
    draw.text((W - 30 - (total_bbox[2]-total_bbox[0]), y), total_fmt, font=font_title, fill='black'); y += 60

    draw_centered("Terima Kasih!", font_bold, y); y += 30

    # IG ICON
    ig_text = "barbershop.keren" # Change to your IG
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

# --- CHECK TIME FUNCTION ---
def get_jam_tersedia(tanggal_pilihan, kapster_pilihan, durasi_layanan_baru, semua_layanan_db):
    try:
        JAM_BUKA_MENIT = 10 * 60  
        JAM_TUTUP_MENIT = 24 * 60 
        
        sheet = get_google_sheet('Booking')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        waktu_sibuk = [] 
        if not df.empty:
            df = df[
                (df['Tanggal'].astype(str) == str(tanggal_pilihan)) & 
                (df['Kapster'] == kapster_pilihan) & 
                (df['Status'] != 'Batal')
            ]
            for _, row in df.iterrows():
                jam_mulai = str_to_menit(row['Jam'])
                nama_lay = str(row['Layanan']).strip()
                durasi_lay = 45 
                for db_name, db_val in semua_layanan_db.items():
                    if str(db_name).strip() == nama_lay:
                        durasi_lay = db_val['Durasi']
                        break
                jam_selesai = jam_mulai + durasi_lay
                waktu_sibuk.append((jam_mulai, jam_selesai))

        list_jam_valid = []
        for menit_start in range(JAM_BUKA_MENIT, JAM_TUTUP_MENIT, 15):
            menit_end = menit_start + durasi_layanan_baru
            if menit_end > JAM_TUTUP_MENIT: continue 
            is_conflict = False
            for sibuk_start, sibuk_end in waktu_sibuk:
                if menit_start < sibuk_end and menit_end > sibuk_start:
                    is_conflict = True
                    break
            if not is_conflict:
                list_jam_valid.append(menit_to_str(menit_start))

        hari_ini_server = datetime.utcnow() + timedelta(hours=7)
        if str(tanggal_pilihan) == str(hari_ini_server.date()):
            menit_sekarang = hari_ini_server.hour * 60 + hari_ini_server.minute
            list_jam_valid = [j for j in list_jam_valid if str_to_menit(j) > menit_sekarang]

        return list_jam_valid
    except Exception as e:
        return ["10:00", "11:00", "12:00"]

# --- CHECK CUSTOMER DATA ---
def get_data_pelanggan(wa_input):
    try:
        wa_target = format_wa_0(wa_input) 
        sheet = get_google_sheet('Pelanggan')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return None
        df.columns = df.columns.str.strip()
        col_target = 'nomor_wa_0'
        if col_target not in df.columns:
            cols = df.columns.tolist()
            for c in cols:
                if 'nomor_wa_0' in str(c).lower(): col_target = c; break
        
        df[col_target] = df[col_target].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
        df[col_target] = df[col_target].apply(lambda x: '0' + x if x.startswith('8') else x)
        hasil = df[df[col_target] == wa_target]
        if not hasil.empty and 'nama_pelanggan' in df.columns:
            return hasil.iloc[0]['nama_pelanggan']
    except Exception as e: print(f"Error Customer Search: {e}")
    return None

# --- SYNC CUSTOMER DATABASE ---
def sync_database_pelanggan(wa_input, nama_final, kapster_pilihan):
    try:
        sheet = get_google_sheet('Pelanggan')
        wa_pk = format_wa_0(wa_input) 
        wa_62 = "62" + wa_pk[1:]
        cell = None
        try: cell = sheet.find(wa_pk)
        except: pass 
        if cell:
            row_idx = cell.row
            sheet.update_cell(row_idx, 4, nama_final) 
            sheet.update_cell(row_idx, 5, kapster_pilihan) 
        else:
            new_row = [wa_input, wa_62, wa_pk, nama_final, kapster_pilihan]
            sheet.append_row(new_row)
        return True
    except Exception as e: print(f"Error Sync: {e}"); return False

# --- GENERATE INVOICE NUMBER ---
def get_next_invoice_number():
    try:
        now = datetime.utcnow() + timedelta(hours=7)
        prefix_bulan = now.strftime("%y%m")
        sheet = get_google_sheet('Pemasukan')
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        next_sequence = 1
        
        if not df.empty and 'Keterangan' in df.columns:          
            import re
            max_seq = 0
            found = False
            for ket in df['Keterangan']:
                match = re.search(rf'\[({prefix_bulan}(\d{{3}}))\]', str(ket))
                if match:
                    found = True
                    seq_int = int(match.group(2))
                    if seq_int > max_seq: max_seq = seq_int
            if found: next_sequence = max_seq + 1
        
        return f"{prefix_bulan}{next_sequence:03d}"
    except: return datetime.now().strftime("%y%m001")

# --- DATABASE WRITE FUNCTIONS ---
def simpan_booking(nama, no_wa, kapster, layanan, tgl, jam):
    try:
        sheet = get_google_sheet('Booking')
        waktu_input = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M:%S")
        data_baru = [str(tgl), jam, nama, str(no_wa), kapster, layanan, "Pending", waktu_input]
        sheet.append_row(data_baru)
        st.cache_data.clear()
        return True
    except Exception as e: st.error(f"Error: {e}"); return False

def proses_pembayaran(baris_ke, nama_pelanggan, list_items, metode_bayar, kapster, diskon_nominal, harga_akhir):
    try:
        sheet_booking = get_google_sheet('Booking')
        sheet_booking.update_cell(baris_ke + 2, 7, "Selesai") 
        no_nota = get_next_invoice_number() 
        try:
            sheet_booking.update_cell(baris_ke + 2, 9, no_nota)
            sheet_booking.update_cell(baris_ke + 2, 11, diskon_nominal)
            sheet_booking.update_cell(baris_ke + 2, 12, harga_akhir)
        except: pass
        
        sheet_uang = get_google_sheet('Pemasukan')
        waktu_obj = datetime.utcnow() + timedelta(hours=7)
        tgl_skrg = waktu_obj.strftime("%Y-%m-%d")
        jam_skrg = waktu_obj.strftime("%H:%M:%S")
        
        rows_to_append = []
        for item in list_items:
            keterangan_lengkap = f"[{no_nota}] {nama_pelanggan} ({metode_bayar}) - {kapster}"
            rows_to_append.append([tgl_skrg, jam_skrg, item['nama'], keterangan_lengkap, item['harga']])
            
        if diskon_nominal > 0:
            ket_diskon = f"[{no_nota}] Promo/Diskon - {kapster}"
            rows_to_append.append([tgl_skrg, jam_skrg, "Potongan Diskon", ket_diskon, -diskon_nominal])
            
        sheet_uang.append_rows(rows_to_append)
        return no_nota 
    except Exception as e: st.error(f"Gagal: {e}"); return None

def batalkan_booking(baris_ke, alasan):
    try:
        sheet_booking = get_google_sheet('Booking')
        sheet_booking.update_cell(baris_ke + 2, 7, "Batal")
        sheet_booking.update_cell(baris_ke + 2, 10, alasan)
        return True
    except Exception as e: st.error(f"Gagal membatalkan: {e}"); return False

def simpan_transaksi_pomade(nama_pomade, nominal, keterangan, link_foto):
    try:
        sheet = get_google_sheet('Pomade')
        w = datetime.utcnow() + timedelta(hours=7)
        sheet.append_row([w.strftime("%Y-%m-%d"), w.strftime("%H:%M:%S"), nama_pomade, nominal, keterangan, link_foto])
        return True
    except Exception as e: st.error(f"Gagal menyimpan data: {e}"); return False

def get_rekap_pomade_harian():
    try:
        sheet = get_google_sheet('Pomade')
        data = sheet.get_all_records()
        if not data: return pd.DataFrame() 
        df = pd.DataFrame(data)
        tgl_hari_ini = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y-%m-%d")
        df_filtered = df[df['Tanggal'] == tgl_hari_ini].copy()
        if 'Tanggal' in df_filtered.columns:
            df_filtered = df_filtered.drop(columns=['Tanggal', 'Link_Bukti'])
        return df_filtered
    except: return pd.DataFrame()
        
def simpan_pengeluaran(nama_pengeluaran, ket_tambahan, nominal):
    try:
        sheet = get_google_sheet('Pengeluaran')
        w = datetime.utcnow() + timedelta(hours=7)
        sheet.append_row([w.strftime("%Y-%m-%d"), w.strftime("%H:%M:%S"), nama_pengeluaran, ket_tambahan, nominal])
        return True
    except: return False

def get_diskon_status():
    try:
        sh = get_google_sheet('Config')
        val = sh.cell(2, 2).value
        return val if val else 'UNLOCKED'
    except: return 'UNLOCKED'

def set_diskon_status(status_baru):
    try:
        sh = get_google_sheet('Config')
        sh.update_cell(2, 2, status_baru)
        st.cache_data.clear()
        return True
    except: return False

# --- MAIN UI ---
# UI Language: Indonesian
menu = st.sidebar.selectbox("Pilih Mode Aplikasi", ["Booking Pelanggan", "Halaman Kasir", "Owner Insight"])

# 1. CUSTOMER BOOKING
if menu == "Booking Pelanggan":
    col_spacer1, col_logo, col_spacer2 = st.columns([1, 2, 1])
    with col_logo:
        if os.path.exists("logo_struk.png"): st.image("logo_struk.png", use_container_width=True)
        else: st.title("💈Barbershop Keren")
    st.write("---")

    # --- FORM CLEANER ---
    if st.session_state.get('sukses_reset', False):
        st.session_state['wa_input_user'] = ""       
        st.session_state['nama_pelanggan_input'] = "" 
        st.session_state['nama_auto'] = ""           
        st.session_state['last_wa_checked'] = ""     
        st.session_state['sukses_reset'] = False     
    
    DATA_LAYANAN = get_daftar_layanan()
    
    list_kapster = ["Kenzo", "Arka"] 
    if 'default_kapster_index' not in st.session_state:
        st.session_state['default_kapster_index'] = random.randint(0, len(list_kapster) - 1)

    kapster = st.selectbox("Pilih Kapster", list_kapster, index=st.session_state['default_kapster_index'], key="pilihan_kapster")

    col_kiri, col_kanan = st.columns([1, 2]) 
    with col_kiri:
        file_foto = INFO_KAPSTER[kapster]['img']
        if os.path.exists(file_foto): st.image(file_foto, width=200, use_container_width=True)
        else: st.image("https://cdn-icons-png.flaticon.com/512/1995/1995539.png", width=150)
            
    with col_kanan:
        st.subheader(f"Profil: {kapster}")
        st.info(INFO_KAPSTER[kapster]['deskripsi'])
        st.write("---")
        layanan_pilihan = st.selectbox("Pilih Layanan", list(DATA_LAYANAN.keys()))
        detail = DATA_LAYANAN[layanan_pilihan]
        st.markdown(f"**⏱️ Durasi:** {detail['Durasi']} Menit") 
        st.caption(f"📝 *Include: {detail['Deskripsi']}*")

        hari_ini_wib = (datetime.utcnow() + timedelta(hours=7)).date()
        tgl = st.date_input("Tanggal Booking", hari_ini_wib, format="DD/MM/YYYY", key="tgl_booking_unik")
        st.caption(f"📅 Pilihan: **{tanggal_indo(tgl)}**")
                            
        durasi_user = detail['Durasi']
        jam_tersedia = get_jam_tersedia(tgl, kapster, durasi_user, DATA_LAYANAN)
        
        if not jam_tersedia:
            st.warning("⚠️ Jadwal Penuh untuk layanan ini.")
            jam = st.selectbox("Jam", ["Penuh"], disabled=True, key="jam_full_disabled"); tombol_aktif = False
        else:
            jam = st.selectbox("Pilih Jam (Interval 15 Menit)", jam_tersedia, key="jam_booking_unik"); tombol_aktif = True
    
    st.write("---") 
    st.subheader("Data Diri Pemesan")

    wa = st.text_input("Nomor WhatsApp (Wajib)", placeholder="Contoh: 0812...", key="wa_input_user")
    pesan_notifikasi = None; tipe_notifikasi = ""

    if 'last_wa_checked' not in st.session_state: st.session_state['last_wa_checked'] = ""
    
    if wa and wa != st.session_state['last_wa_checked']:
        with st.spinner("Mengecek data pelanggan..."):
            nama_di_db = get_data_pelanggan(wa)
            if nama_di_db:
                st.session_state['nama_pelanggan_input'] = nama_di_db
                pesan_notifikasi = f"Halo Kak {nama_di_db}, Selamat datang kembali! 🤝"; tipe_notifikasi = "success"
            else:
                if 'nama_pelanggan_input' in st.session_state: st.session_state['nama_pelanggan_input'] = ""
                pesan_notifikasi = "Halo pelanggan baru! Silakan isi nama Kakak ya. 😊"; tipe_notifikasi = "info"
        st.session_state['last_wa_checked'] = wa

    nama = st.text_input("Nama Pelanggan", placeholder="Nama Anda...", key="nama_pelanggan_input")
    
    if pesan_notifikasi:
        if tipe_notifikasi == "success": st.success(pesan_notifikasi, icon="✅")
        else: st.info(pesan_notifikasi, icon="👋")
    
    st.write("---")

    if st.button("Booking Sekarang", type="primary", disabled=not tombol_aktif, use_container_width=True):
        if nama and wa and jam != "Penuh":
            with st.spinner("Mendaftarkan Booking..."):
                sukses_booking = simpan_booking(nama, wa, kapster, layanan_pilihan, tgl, jam)
                if sukses_booking:
                    sync_database_pelanggan(wa, nama, kapster)
                    st.success(f"✅ Booking Berhasil! Sampai jumpa {nama}.")
                    st.snow()
                    st.session_state['sukses_reset'] = True 
                    time.sleep(3)
                    st.rerun()
        else: st.warning("Mohon lengkapi Nama dan No WA.")

# 2. CASHIER PAGE
elif menu == "Halaman Kasir":
    st.title("💼 Dashboard Kasir")
    password = st.sidebar.text_input("Password", type="password")
    DATA_LAYANAN = get_daftar_layanan() 

    if password == "kasirsecrets":
        st.sidebar.success("Login Berhasil")
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔴 Antrian & Bayar", "✅ Riwayat", "💰 Pengeluaran", "📊 Lapor Bos", "🏆 Mingguan", "🧴 Pomade"])
        
        # TAB 1: CASHIER
        with tab1:
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
                    for it in data_nota['items']: rincian_text += f"• {it['nama']} (Rp {it['harga']:,})\n"
                    
                    pesan_tambahan = ""
                    if 'diskon' in data_nota and data_nota['diskon'] > 0:
                         pesan_tambahan = f"\n(Diskon: -Rp {data_nota['diskon']:,})\n*Total Bayar: Rp {data_nota['total_final']:,}*"

                    pesan_nota = (f"Halo Kak *{data_nota['nama']}*! 👋\nTerima kasih sudah mampir di *Barbershop Keren*.\n\n*Rincian:*\n{rincian_text}{pesan_tambahan}\nKeren banget hasilnya! Ditunggu kedatangannya lagi. 💈")
                    link_wa_nota = f"https://wa.me/{hp_fmt}?text={urllib.parse.quote(pesan_nota)}"
                    st.link_button("💬 2. Chat Pengantar Nota", link_wa_nota)
                    st.write("---")
                    if st.button("Tutup / Transaksi Baru"): st.session_state['nota_terakhir'] = None; st.rerun()
            else:
                if st.button("🔄 Refresh Data Antrian"): st.rerun()
                st.subheader("📋 Daftar Antrian Booking")
                try:
                    sheet = get_google_sheet('Booking')
                    data = sheet.get_all_records()
                    df = pd.DataFrame(data)
                    if not df.empty:
                        df.columns = df.columns.str.strip()
                        if 'Waktu' in df.columns and 'Jam' not in df.columns: df.rename(columns={'Waktu': 'Jam'}, inplace=True)
                    
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
                                
                                st.markdown("#### 🚀 Upgrade Layanan (Opsional)")
                                cek_upgrade = st.checkbox("Pelanggan ganti ke paket lebih mahal?")
                                item_upgrade_diff = None; nama_layanan_final = lay_awal
                                
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
                                
                                list_belanja = []; total_tagihan_normal = 0
                                harga_base = 0
                                for db_n, db_v in DATA_LAYANAN.items():
                                    if str(db_n).strip() == str(lay_awal).strip(): harga_base = db_v['Harga']; break
                                list_belanja.append({'nama': f"Jasa {nama_layanan_final}", 'harga': harga_base})
                                total_tagihan_normal += harga_base
                                if item_upgrade_diff: list_belanja.append(item_upgrade_diff); total_tagihan_normal += item_upgrade_diff['harga']
                                for tamb in layanan_tambahan:
                                    h_tamb = DATA_LAYANAN[tamb]['Harga']
                                    list_belanja.append({'nama': f"Add-on {tamb}", 'harga': h_tamb})
                                    total_tagihan_normal += h_tamb
                                
                                st.write("---")
                                c1, c2, c3 = st.columns([1, 1.5, 1])
                                with c1:
                                    st.caption("📢 Info & Reminder:")
                                    pesan_wa = (f"Halo Kak *{nam}*, kami mengingatkan booking jam *{jam_bk}* ya. Sampai jumpa! 💈")
                                    st.link_button("💬 Chat Reminder", f"https://wa.me/{format_nomor_wa(no_hp)}?text={urllib.parse.quote(pesan_wa)}")
                                    st.write("---")
                                    st.caption(f"🛒 Rincian ({len(list_belanja)} Item):")
                                    for item in list_belanja: st.text(f"- {item['nama']}")
                                with c2:
                                    status_izin = get_diskon_status()
                                    nominal_diskon = 0; total_final = total_tagihan_normal
                                    
                                    if status_izin == 'UNLOCKED':
                                        st.markdown("##### 🏷️ Diskon")
                                        jenis_disc = st.radio("Tipe", ["Tanpa Diskon", "Rupiah", "Persen"], horizontal=True, label_visibility="collapsed")
                                        if jenis_disc == "Rupiah": nominal_diskon = st.number_input("Nominal", min_value=0, step=1000)
                                        elif jenis_disc == "Persen": nominal_diskon = total_tagihan_normal * (st.number_input("Persen", 0, 100, 5) / 100)
                                    else:
                                        st.markdown("##### 🏷️ Diskon"); st.info("🔒 Terkunci"); nominal_diskon = 0
                                    
                                    total_final = max(0, total_tagihan_normal - nominal_diskon)
                                    if nominal_diskon > 0:
                                        st.caption(f"Normal: {total_tagihan_normal:,} | Disc: -{int(nominal_diskon):,}")
                                        st.markdown(f"#### Total: Rp {int(total_final):,}")
                                    else: st.metric("Total Tagihan", f"Rp {total_tagihan_normal:,}")

                                    st.write("---")
                                    metode = st.radio("Metode Bayar:", ["Tunai", "QRIS"], horizontal=True)
                                    tombol_aman = True
                                    if cek_upgrade and selisih < 0: tombol_aman = False
                                    
                                    if tombol_aman and total_final >= 0:
                                        if st.button("✅ Bayar & Cetak", type="primary"):
                                            nama_simpan = nam
                                            if item_upgrade_diff: nama_simpan = f"{nam} [UPGRADE]"
                                            no_nota_hasil = proses_pembayaran(idx, nama_simpan, list_belanja, metode, kap, int(nominal_diskon), int(total_final))
                                            if no_nota_hasil:
                                                img = generate_receipt_image(nam, list_belanja, total_tagihan_normal, int(nominal_diskon), int(total_final), kap, tgl_bk, jam_bk, no_nota_hasil)
                                                st.session_state['nota_terakhir'] = {'img': img, 'nama': nam, 'wa': no_hp, 'items': list_belanja, 'total_normal': total_tagihan_normal, 'diskon': int(nominal_diskon), 'total_final': int(total_final)}
                                                st.cache_data.clear(); st.rerun()
                                    elif not tombol_aman: st.error("Perbaiki pilihan upgrade.")
                                with c3:
                                    with st.popover("❌ Batal"):
                                        st.write(f"Batalkan {nam}?")
                                        alasan_batal = st.text_input("Alasan (Wajib)", placeholder="No Show")
                                        if st.button("Ya, Hapus"):
                                            if alasan_batal:
                                                if batalkan_booking(idx, alasan_batal): st.toast("Dibatalkan!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                                            else: st.error("Isi alasan.")
                        else: st.info("Antrian kosong.")
                    else: st.info("Data kosong.")
                except Exception as e: st.error(f"Error: {e}")

                st.write("---")
                with st.expander("⚡ Transaksi Langsung (Go Show / Tanpa Booking)", expanded=False):
                    st.caption("Menu ini hanya digunakan ketika pelanggan datang langsung dan jadwal kapster di halaman pelanggan tidak tersedia.")
                    
                    if st.session_state.get('reset_go_show', False):
                        st.session_state['go_wa'] = ""; st.session_state['go_nama'] = ""; st.session_state['go_last_wa'] = ""; st.session_state['reset_go_show'] = False

                    go_wa = st.text_input("No WA (Enter untuk Cek)", key="go_wa")
                    if 'go_last_wa' not in st.session_state: st.session_state['go_last_wa'] = ""
                    if go_wa and go_wa != st.session_state['go_last_wa']:
                        with st.spinner("Cek data..."):
                            hasil_nama = get_data_pelanggan(go_wa)
                            if hasil_nama: st.session_state['go_nama'] = hasil_nama 
                            else: st.info("Pelanggan Baru."); st.session_state['go_nama'] = "" 
                        st.session_state['go_last_wa'] = go_wa

                    go_nama = st.text_input("Nama Pelanggan", key="go_nama")
                    c_go1, c_go2 = st.columns(2)
                    with c_go1:
                        go_kapster = st.selectbox("Pilih Kapster", list(INFO_KAPSTER.keys()), key="go_kapster")
                        go_layanan = st.selectbox("Pilih Layanan", list(DATA_LAYANAN.keys()), key="go_layanan")
                    with c_go2:
                        opsi_go_addon = list(DATA_LAYANAN.keys())
                        if go_layanan in opsi_go_addon: opsi_go_addon.remove(go_layanan)
                        go_addon = st.multiselect("Tambahan", opsi_go_addon, key="go_addon")
                        go_metode = st.radio("Metode Bayar", ["Tunai", "QRIS"], horizontal=True, key="go_metode")

                    go_total_normal = 0; go_items = []
                    hrg_utama = 0
                    for db_n, db_v in DATA_LAYANAN.items():
                        if str(db_n).strip() == str(go_layanan).strip(): hrg_utama = db_v['Harga']; break
                    go_items.append({'nama': f"Jasa {go_layanan}", 'harga': hrg_utama})
                    go_total_normal += hrg_utama
                    for add in go_addon:
                        h_add = DATA_LAYANAN[add]['Harga']; go_items.append({'nama': f"Add-on {add}", 'harga': h_add}); go_total_normal += h_add
                    
                    st.write("---")
                    status_izin_go = get_diskon_status(); go_nominal_diskon = 0
                    if status_izin_go == 'UNLOCKED':
                        c_d1, c_d2 = st.columns([1, 1])
                        with c_d1: go_jenis_disc = st.radio("Diskon", ["Tanpa Diskon", "Rupiah", "Persen"], horizontal=True, key="go_type_disc")
                        if go_jenis_disc == "Rupiah":
                            with c_d2: go_nominal_diskon = st.number_input("Nominal", step=1000, key="go_val_rp")
                        elif go_jenis_disc == "Persen":
                            with c_d2: go_pct = st.number_input("Persen", 0, 100, 5, key="go_val_pct"); go_nominal_diskon = go_total_normal * (go_pct/100)
                    else: st.info("🔒 Diskon Terkunci"); go_nominal_diskon = 0

                    go_total_final = max(0, go_total_normal - go_nominal_diskon)
                    st.markdown(f"**Total Akhir: Rp {int(go_total_final):,}** *(Normal: {int(go_total_normal):,} | Disc: {int(go_nominal_diskon):,})*".replace(',', '.'))
                    
                    if st.button("Proses Transaksi", type="primary"):
                        if go_nama and go_wa:
                            with st.spinner("Memproses..."):
                                sync_database_pelanggan(go_wa, go_nama, go_kapster)
                                now_obj = datetime.utcnow() + timedelta(hours=7)
                                try:
                                    sheet_bk = get_google_sheet('Booking')
                                    waktu_input = now_obj.strftime("%Y-%m-%d %H:%M:%S")
                                    sheet_bk.append_row([now_obj.strftime("%Y-%m-%d"), now_obj.strftime("%H:%M"), go_nama, format_wa_0(go_wa), go_kapster, go_layanan, "Proses..", waktu_input, ""])
                                    idx_fungsi = len(sheet_bk.get_all_values()) - 2
                                    no_nota = proses_pembayaran(idx_fungsi, go_nama, go_items, go_metode, go_kapster, int(go_nominal_diskon), int(go_total_final))
                                    if no_nota:
                                        img = generate_receipt_image(go_nama, go_items, go_total_normal, int(go_nominal_diskon), int(go_total_final), go_kapster, now_obj.strftime("%Y-%m-%d"), now_obj.strftime("%H:%M"), no_nota)
                                        st.session_state['reset_go_show'] = True
                                        st.session_state['nota_terakhir'] = {'img': img, 'nama': go_nama, 'wa': go_wa, 'items': go_items, 'total_normal': go_total_normal, 'diskon': int(go_nominal_diskon), 'total_final': int(go_total_final)}
                                        st.cache_data.clear(); st.rerun()
                                except Exception as e: st.error(f"Gagal: {e}")
                        else: st.warning("Nama dan WA wajib diisi.")

        # TAB 2
        with tab2:
            st.header("✅ Riwayat & Cetak Ulang")
            try:
                sheet = get_google_sheet('Booking'); data = sheet.get_all_records(); df = pd.DataFrame(data)
                if not df.empty:
                    if 'Waktu' in df.columns: df.rename(columns={'Waktu': 'Jam'}, inplace=True)
                    if 'Jam' in df.columns:
                        col_tgl1, col_tgl2 = st.columns([1, 2])
                        with col_tgl1: tgl_filter = st.date_input("Pilih Tanggal", datetime.now())
                        df_filtered = df[df['Tanggal'].astype(str) == str(tgl_filter)].copy()
                        if not df_filtered.empty:
                            df_filtered = df_filtered.sort_values(by='Jam', ascending=False)
                            if 'No_WA' in df_filtered.columns: df_filtered['No_WA'] = df_filtered['No_WA'].apply(format_wa_0)
                            df_filtered.insert(0, 'No', range(1, len(df_filtered) + 1))
                            cols = [k for k in ['No', 'Jam', 'Nama_Pelanggan', 'No_WA', 'Layanan', 'Kapster', 'Status', 'No_Nota'] if k in df_filtered.columns]
                            st.dataframe(df_filtered[cols], use_container_width=True, hide_index=True)
                            st.write("---")
                            st.subheader("🖨️ Cetak Ulang Struk")
                            df_siap = df_filtered[df_filtered.get('Status') == 'Selesai'].reset_index() if 'Status' in df_filtered.columns else df_filtered.reset_index()
                            if not df_siap.empty:
                                opsi = []
                                for i, row in df_siap.iterrows():
                                    nota_txt = f"[{row['No_Nota']}] " if 'No_Nota' in row and str(row['No_Nota']).strip() else "[LAMA] "
                                    opsi.append((i, f"{nota_txt}{row['Jam']} - {row['Nama_Pelanggan']}"))
                                pilihan = st.selectbox("Pilih Transaksi:", opsi, format_func=lambda x: x[1])
                                if pilihan and st.button("Cetak Struk"):
                                    idx_sel, _ = pilihan; d_row = df_siap.iloc[idx_sel]
                                    no_nota = str(d_row.get('No_Nota', '')).strip()
                                    if not no_nota: st.error("⚠️ Transaksi lama tanpa nota.")
                                    else:
                                        items = []; total = 0
                                        with st.spinner("Mengambil data..."):
                                            try:
                                                sheet_uang = get_google_sheet('Pemasukan'); df_uang = pd.DataFrame(sheet_uang.get_all_records())
                                                if not df_uang.empty:
                                                    df_match = df_uang[df_uang['Keterangan'].str.contains(f"[{no_nota}]", regex=False, na=False)]
                                                    for _, r in df_match.iterrows():
                                                        nom = int(str(r['Nominal']).replace('.','').replace(',',''))
                                                        items.append({'nama': r['Item'], 'harga': nom}); total += nom
                                            except: pass
                                        if not items: items = [{'nama': f"Jasa {d_row['Layanan']}", 'harga': 0}]; st.warning("Data default.")
                                        img = generate_receipt_image(d_row['Nama_Pelanggan'], items, total, 0, total, d_row['Kapster'], str(tgl_filter), str(d_row['Jam']), no_nota)
                                        c1, c2 = st.columns([1, 1.5]); c1.image(img, width=200)
                                        buf = io.BytesIO(); img.save(buf, format="PNG"); byte_im = buf.getvalue()
                                        c2.download_button("⬇️ Download PNG", byte_im, f"Struk_{no_nota}.png", "image/png")
                            else: st.info("Belum ada transaksi selesai.")
                        else: st.info("Tidak ada data.")
                else: st.info("Data kosong.")
            except Exception as e: st.error(f"Error: {e}")

        # TAB 3
        with tab3:
            st.header("💰 Catat Pengeluaran")
            list_rek = ["Laundry Handuk", "Token Listrik"]
            try:
                sheet_out = get_google_sheet('Pengeluaran'); df_out = pd.DataFrame(sheet_out.get_all_records())
                if not df_out.empty and 'Item' in df_out.columns:
                    list_rek = sorted(list(set(list_rek + df_out['Item'].unique().tolist())))
            except: pass 
            list_rek.insert(0, "📝 Input Nama Baru...")
            pilih = st.selectbox("1. Nama Pengeluaran (Ketik untuk cari)", list_rek, index=1)
            nama_final = st.text_input("👉 Ketik Nama") if pilih == "📝 Input Nama Baru..." else pilih
            nom = st.number_input("2. Nominal (Rp)", min_value=0, step=1000)
            ket = st.text_input("3. Keterangan Tambahan", placeholder="Opsional")
            st.write("---")
            if st.button("Simpan Pengeluaran", type="primary"):
                if nama_final and nom > 0:
                    if simpan_pengeluaran(nama_final, ket, nom): st.success("✅ Disimpan!"); st.cache_data.clear(); time.sleep(1.5); st.rerun()
                else: st.warning("Isi data lengkap.")

        # TAB 4
        with tab4:
            st.header("📊 Laporan Harian")
            st.caption("Pilih tanggal, cek data, lalu kirim rekap lengkap ke WA.")
            now_wib = datetime.utcnow() + timedelta(hours=7)
            tgl_laporan = st.date_input("Pilih Tanggal Laporan:", now_wib)
            tgl_str = tgl_laporan.strftime("%Y-%m-%d")
            st.write("---")

            if st.button(f"Hitung Rekap Tanggal {tanggal_indo(tgl_laporan)}"):
                try:
                    df_masuk = pd.DataFrame(); df_keluar = pd.DataFrame(); df_bk = pd.DataFrame()
                    try:
                        sheet_in = get_google_sheet('Pemasukan'); df_in = pd.DataFrame(sheet_in.get_all_records())
                        if not df_in.empty: df_in['Tanggal'] = df_in['Tanggal'].astype(str); df_masuk = df_in[df_in['Tanggal'] == tgl_str]
                    except: pass
                    try:
                        sheet_out = get_google_sheet('Pengeluaran'); df_out = pd.DataFrame(sheet_out.get_all_records())
                        if not df_out.empty: df_out['Tanggal'] = df_out['Tanggal'].astype(str); df_keluar = df_out[df_out['Tanggal'] == tgl_str]
                    except: pass
                    try:
                        sheet_b = get_google_sheet('Booking'); df_b = pd.DataFrame(sheet_b.get_all_records())
                        if not df_b.empty: df_b['Tanggal'] = df_b['Tanggal'].astype(str); df_bk = df_b[(df_b['Tanggal'] == tgl_str) & (df_b['Status'] == 'Selesai')]
                    except: pass

                    tot_masuk = df_masuk['Nominal'].sum() if not df_masuk.empty else 0
                    tot_keluar = df_keluar['Nominal'].sum() if not df_keluar.empty else 0
                    tot_cash = 0; count_cash = 0; tot_qris = 0; count_qris = 0
                    
                    if not df_masuk.empty:
                        mask_c = df_masuk['Keterangan'].str.contains("Tunai", case=False, na=False)
                        tot_cash = df_masuk[mask_c]['Nominal'].sum(); count_cash = len(df_masuk[mask_c])
                        mask_q = df_masuk['Keterangan'].str.contains("QRIS", case=False, na=False)
                        tot_qris = df_masuk[mask_q]['Nominal'].sum(); count_qris = len(df_masuk[mask_q])
                    
                    # HITUNG DISKON HARI INI
                    tot_disc = 0
                    if not df_bk.empty and 'Diskon' in df_bk.columns:
                        def clean(x):
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        tot_disc = df_bk['Diskon'].apply(clean).sum()

                    net_cash = tot_cash - tot_keluar
                    c1,c2,c3,c4 = st.columns(4)
                    c1.metric("QRIS", f"{tot_qris:,}".replace(',', '.'), f"{count_qris} Trx")
                    c2.metric("Cash In", f"{tot_cash:,}".replace(',', '.'), f"{count_cash} Trx")
                    c3.metric("Cash Out", f"{tot_keluar:,}".replace(',', '.'))
                    c4.metric("Net Cash", f"{net_cash:,}".replace(',', '.'))
                    
                    st.write("---")
                    c_tbl1, c_tbl2 = st.columns(2)
                    with c_tbl1:
                        st.subheader("📥 Pemasukan")
                        if not df_masuk.empty: st.dataframe(df_masuk[['Item', 'Nominal']], hide_index=True, use_container_width=True)
                        else: st.info("Kosong")
                    with c_tbl2:
                        st.subheader("📤 Pengeluaran")
                        if not df_keluar.empty: st.dataframe(df_keluar[['Item', 'Nominal']], hide_index=True, use_container_width=True)
                        else: st.info("Kosong")

                    txt_kap = ""; txt_lay = ""
                    if not df_bk.empty:
                        for k, v in df_bk['Kapster'].value_counts().items(): txt_kap += f"✂️ {k}: {v}\n"
                        for k, v in df_bk['Layanan'].value_counts().items(): txt_lay += f"💈 {k}: {v}\n"
                    
                    txt_out = ""
                    if not df_keluar.empty:
                        for _, r in df_keluar.iterrows(): txt_out += f"• {r['Item']}: {r['Nominal']:,}\n".replace(',', '.')

                    txt_disc = ""
                    if tot_disc > 0: txt_disc = f"(Diskon Diberikan: Rp {tot_disc:,})".replace(',', '.') + "\n"

                    msg = (f"*LAPORAN HARIAN*\n📅 {tanggal_indo(tgl_laporan)}\n----------------\n*STATISTIK:*\n{txt_kap}\n{txt_lay}\n*KEUANGAN:*\nCash: {tot_cash:,}\nQRIS: {tot_qris:,}\nTotal Revenue: *{tot_masuk:,}*\n{txt_disc}\nTotal Expense: {tot_keluar:,}\n----------------\n*NET CASH: {net_cash:,}*".replace(',', '.'))
                    st.link_button("📤 Kirim WA", f"https://wa.me/?text={urllib.parse.quote(msg)}", type="primary")
                except Exception as e: st.error(f"Error: {e}")

        # TAB 5
        with tab5:
            st.header("🏆 Laporan Mingguan")
            tgl_pilih = st.date_input("Pilih Tanggal", datetime.now())
            start_week = tgl_pilih - timedelta(days=tgl_pilih.weekday())
            end_week = start_week + timedelta(days=6)
            st.info(f"Periode: **{tanggal_indo(start_week)} - {tanggal_indo(end_week)}**")
            
            if st.button("Analisis"):
                try:
                    sheet_in = get_google_sheet('Pemasukan'); df_in = pd.DataFrame(sheet_in.get_all_records())
                    if not df_in.empty:
                        df_in['Tanggal'] = pd.to_datetime(df_in['Tanggal']).dt.date
                        df_in = df_in[(df_in['Tanggal'] >= start_week) & (df_in['Tanggal'] <= end_week)]
                        def clean(x): 
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        df_in['Nominal'] = df_in['Nominal'].apply(clean)

                        kapsters = list(INFO_KAPSTER.keys())
                        laporan = {}; t_gross = 0; t_disc = 0; t_net = 0; t_kepala = 0

                        for k in kapsters:
                            df_k = df_in[df_in['Keterangan'].str.contains(f"- {k}", case=False, na=False)].copy()
                            if df_k.empty: 
                                laporan[k] = {'kepala':0, 'gross':0, 'disc':0, 'net':0, 'details':[]}
                                continue
                            
                            df_k['Nota_ID'] = df_k['Keterangan'].str.extract(r'\[(\w+)\]')
                            grouped = df_k.groupby('Nota_ID')
                            stats_menu = {}; k_gross = 0; k_disc = 0; k_net = 0; count_kepala = 0

                            for nota, group in grouped:
                                count_kepala += 1
                                items_pos = group[group['Nominal'] > 0].to_dict('records')
                                items_neg = group[group['Nominal'] < 0]['Nominal'].sum()
                                
                                # Logic Merge Upgrade
                                tot_upg = sum([x['Nominal'] for x in items_pos if "biaya upgrade" in str(x['Item']).lower()])
                                target_idx = -1
                                for i, item in enumerate(items_pos):
                                    if "up from" in str(item['Item']).lower(): target_idx = i; break
                                
                                final_items = []
                                if target_idx != -1 and tot_upg > 0:
                                    for i, item in enumerate(items_pos):
                                        if i == target_idx:
                                            new_nom = item['Nominal'] + tot_upg
                                            new_name = item['Item'].split(' (Up from')[0].strip()
                                            final_items.append({'Item': new_name, 'Nominal': new_nom})
                                        elif "biaya upgrade" in str(item['Item']).lower(): continue
                                        else: final_items.append(item)
                                else: final_items = items_pos

                                nota_gross = 0
                                for f in final_items:
                                    nm = f['Item']; nom = f['Nominal']; nota_gross += nom
                                    if nm not in stats_menu: stats_menu[nm] = {'qty': 0, 'gross': 0}
                                    stats_menu[nm]['qty'] += 1; stats_menu[nm]['gross'] += nom
                                
                                k_gross += nota_gross; k_disc += abs(items_neg); k_net += (nota_gross - abs(items_neg))

                            detail_list = []
                            for m, s in stats_menu.items(): detail_list.append({'Menu': m, 'Qty': s['qty'], 'Gross': s['gross']})
                            if k_disc > 0: detail_list.append({'Menu': '🔻 Diskon', 'Qty': df_k[df_k['Nominal'] < 0].shape[0], 'Gross': -k_disc})

                            laporan[k] = {'kepala': count_kepala, 'gross': k_gross, 'disc': k_disc, 'net': k_net, 'details': detail_list}
                            t_gross += k_gross; t_disc += k_disc; t_net += k_net; t_kepala += count_kepala

                        st.write("---")
                        c1,c2,c3,c4 = st.columns(4)
                        c1.metric("Total Kepala", t_kepala)
                        c2.metric("Total Gross", f"{t_gross:,}".replace(',', '.'))
                        c3.metric("Total Discount", f"{t_disc:,}".replace(',', '.'), delta_color="inverse")
                        c4.metric("Total Net", f"{t_net:,}".replace(',', '.'))
                        st.write("---")
                        
                        c1, c2 = st.columns(2)
                        for i, k in enumerate(kapsters):
                            d = laporan[k]
                            with (c1 if i%2==0 else c2):
                                st.markdown(f"### 💈 {k}")
                                st.image(INFO_KAPSTER[k]['img'], width=100)
                                m1, m2 = st.columns([1, 2])
                                m1.metric("✂️ Heads", d['kepala']); m2.metric("💰 Net", f"{d['net']:,}".replace(',', '.'))
                                if d['details']:
                                    df_d = pd.DataFrame(d['details']).sort_values(by='Qty', ascending=False)
                                    df_d['Gross'] = df_d['Gross'].apply(lambda x: f"{int(x):,}".replace(',', '.'))
                                    st.dataframe(df_d, hide_index=True, use_container_width=True)
                        
                        msg = f"*WEEKLY REPORT*\nPeriod: {tanggal_indo(start_week)} - {tanggal_indo(end_week)}\n================\n"
                        for k in kapsters:
                            d = laporan[k]
                            msg += f"💈 {k}\n   ✂️ {d['kepala']} Heads | Net: {d['net']:,}\n".replace(',', '.')
                            if d['disc']>0: msg += f"   (Disc: {d['disc']:,})\n".replace(',', '.')
                            msg += "----------------\n"
                        msg += f"🏢 TOTAL: {t_net:,}".replace(',', '.')
                        st.link_button("📤 Send WA", f"https://wa.me/?text={urllib.parse.quote(msg)}", type="primary")
                    else: st.warning("Data Empty")
                except Exception as e: st.error(f"Error: {e}")

        # TAB 6
        with tab6:
            st.header("📸 Product Sales")
            col_input, col_rekap = st.columns([1, 1])
            with col_input:
                st.subheader("Input Sales")
                with st.form("form_pomade", clear_on_submit=True):
                    nama_p = st.text_input("Product Name", placeholder="Blue Water Based")
                    harga_p = st.number_input("Amount (Rp)", min_value=0, step=1000)
                    ket_p = st.text_area("Notes", placeholder="Discount...")
                    st.write("---")
                    st.caption("Photo Proof (Required)")
                    gambar_pomade = st.file_uploader("Upload Photo", type=['jpg', 'png', 'jpeg'])
                    submit_pomade = st.form_submit_button("Save & Upload", type="primary")
                    if submit_pomade:
                        if not nama_p or harga_p <= 0: st.warning("Fill Name & Amount.")
                        elif not gambar_pomade: st.error("PHOTO REQUIRED!")
                        else:
                            with st.spinner("Uploading..."):
                                waktu_file = (datetime.utcnow() + timedelta(hours=7)).strftime("%Y%m%d_%H%M%S")
                                ext = gambar_pomade.name.split('.')[-1]
                                link_hasil = upload_ke_drive(gambar_pomade, f"PRODUK_{nama_p}_{waktu_file}.{ext}")
                                if link_hasil:
                                    if simpan_transaksi_pomade(nama_p, int(harga_p), ket_p, link_hasil):
                                        st.success(f"✅ Sold: {nama_p}"); time.sleep(1); st.rerun()
                                else: st.error("Upload Failed.")
            with col_rekap:
                st.subheader("📊 Daily Recap")
                if st.button("🔄 Refresh Data"): st.rerun()
                df_pomade = get_rekap_pomade_harian()
                if not df_pomade.empty:
                    st.metric("Total Today", f"Rp {df_pomade['Nominal'].sum():,}")
                    st.dataframe(df_pomade, hide_index=True, use_container_width=True)
                else: st.info("No sales yet.")

    elif password: st.error("Wrong Password!")

# ==========================================
# 3. OWNER INSIGHT PAGE
# ==========================================
elif menu == "Owner Insight":
    st.title("📈 Owner Insight")
    pass_owner = st.sidebar.text_input("Owner Password", type="password")
    
    if pass_owner == "BERKAT2026":
        st.sidebar.success("Access Granted ✅")
        
        # --- DISCOUNT CONTROL ---
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            curr = get_diskon_status(); is_unlock = (curr == 'UNLOCKED')
            with c1: mode = st.toggle("Unlock Discount?", value=is_unlock)
            with c2:
                new_s = 'UNLOCKED' if mode else 'LOCKED'
                if new_s != curr: set_diskon_status(new_s); st.rerun()
                if mode: st.success("✅ Cashier CAN Discount")
                else: st.error("🔒 Discount LOCKED")

        DATA_LAYANAN = get_daftar_layanan() 
        t1, t2, t3 = st.tabs(["📅 Monthly Performance", "💸 Owner Expenses", "💵 Profit & Share"])
        
        # --- OWNER TAB 1: MONTHLY ---
        with t1:
            st.header("Monthly Analysis")
            c_b1, c_b2 = st.columns(2)
            with c_b1: bln = st.selectbox("Select Month", range(1, 13), index=datetime.now().month - 1)
            with c_b2: thn = st.number_input("Select Year", value=datetime.now().year)
            
            if st.button("Show"):
                try:
                    sheet_in = get_google_sheet('Pemasukan'); df_in = pd.DataFrame(sheet_in.get_all_records())
                    if not df_in.empty:
                        df_in['Tanggal'] = pd.to_datetime(df_in['Tanggal'])
                        df_in = df_in[(df_in['Tanggal'].dt.month == bln) & (df_in['Tanggal'].dt.year == thn)]
                        def clean(x): 
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        df_in['Nominal'] = df_in['Nominal'].apply(clean)

                        kapsters = list(INFO_KAPSTER.keys())
                        laporan = {}; t_gross = 0; t_disc = 0; t_net = 0; t_kepala = 0

                        for k in kapsters:
                            df_k = df_in[df_in['Keterangan'].str.contains(f"- {k}", case=False, na=False)].copy()
                            if df_k.empty: 
                                laporan[k] = {'kepala':0, 'gross':0, 'disc':0, 'net':0, 'details':[]}
                                continue
                            
                            df_k['Nota_ID'] = df_k['Keterangan'].str.extract(r'\[(\w+)\]')
                            grouped = df_k.groupby('Nota_ID')
                            stats_menu = {}; k_gross = 0; k_disc = 0; k_net = 0; count_kepala = 0

                            for nota, group in grouped:
                                count_kepala += 1
                                items_pos = group[group['Nominal'] > 0].to_dict('records')
                                items_neg = group[group['Nominal'] < 0]['Nominal'].sum()
                                
                                # Logic Merge Upgrade
                                tot_upg = sum([x['Nominal'] for x in items_pos if "biaya upgrade" in str(x['Item']).lower()])
                                target_idx = -1
                                for i, item in enumerate(items_pos):
                                    if "up from" in str(item['Item']).lower(): target_idx = i; break
                                
                                final_items = []
                                if target_idx != -1 and tot_upg > 0:
                                    for i, item in enumerate(items_pos):
                                        if i == target_idx:
                                            new_nom = item['Nominal'] + tot_upg
                                            new_name = item['Item'].split(' (Up from')[0].strip()
                                            final_items.append({'Item': new_name, 'Nominal': new_nom})
                                        elif "biaya upgrade" in str(item['Item']).lower(): continue
                                        else: final_items.append(item)
                                else: final_items = items_pos

                                nota_gross = 0
                                for f in final_items:
                                    nm = f['Item']; nom = f['Nominal']; nota_gross += nom
                                    if nm not in stats_menu: stats_menu[nm] = {'qty': 0, 'gross': 0}
                                    stats_menu[nm]['qty'] += 1; stats_menu[nm]['gross'] += nom
                                
                                k_gross += nota_gross; k_disc += abs(items_neg); k_net += (nota_gross - abs(items_neg))

                            detail_list = []
                            for m, s in stats_menu.items(): detail_list.append({'Menu': m, 'Qty': s['qty'], 'Gross': s['gross']})
                            if k_disc > 0: detail_list.append({'Menu': '🔻 Discount', 'Qty': df_k[df_k['Nominal'] < 0].shape[0], 'Gross': -k_disc})

                            laporan[k] = {'kepala': count_kepala, 'gross': k_gross, 'disc': k_disc, 'net': k_net, 'details': detail_list}
                            t_gross += k_gross; t_disc += k_disc; t_net += k_net; t_kepala += count_kepala
                        
                        st.write("---")
                        c1,c2,c3,c4 = st.columns(4)
                        c1.metric("Total Heads", t_kepala)
                        c2.metric("Total Gross", f"{t_gross:,}".replace(',', '.'))
                        c3.metric("Total Discount", f"{t_disc:,}".replace(',', '.'), delta_color="inverse")
                        c4.metric("Total Net", f"{t_net:,}".replace(',', '.'))
                        
                        st.write("---")
                        c1, c2 = st.columns(2)
                        for i, k in enumerate(kapsters):
                            d = laporan[k]
                            with (c1 if i%2==0 else c2):
                                st.markdown(f"### 💈 {k}")
                                st.image(INFO_KAPSTER[k]['img'], width=100)
                                m1, m2 = st.columns([1, 2])
                                m1.metric("✂️ Heads", d['kepala']); m2.metric("💰 Net", f"{d['net']:,}".replace(',', '.'))
                                if d['details']:
                                    df_d = pd.DataFrame(d['details']).sort_values(by='Qty', ascending=False)
                                    df_d['Gross'] = df_d['Gross'].apply(lambda x: f"{int(x):,}".replace(',', '.'))
                                    st.dataframe(df_d, hide_index=True, use_container_width=True)
                        
                        # CHART
                        st.subheader("📊 Monthly Chart")
                        chart_df = pd.DataFrame({'Kapster': kapsters, 'Total Heads': [laporan[k]['kepala'] for k in kapsters]})
                        st.altair_chart(alt.Chart(chart_df).mark_bar().encode(x='Kapster', y='Total Heads'), use_container_width=True)
                    else: st.warning("Data Empty")
                except Exception as e: st.error(f"Error: {e}")

        # --- OWNER TAB 2: EXPENSES ---
        with t2:
            st.header("💰 Owner Expenses")
            list_rek = ["Gaji Kapster", "Sewa Ruko", "Belanja Logistik", "Maintenance"]
            pilih = st.selectbox("Expense Name", list_rek + ["New Input..."])
            nama = st.text_input("Type Name") if pilih == "New Input..." else pilih
            nom = st.number_input("Amount", step=10000)
            ket = st.text_input("Notes")
            
            if st.button("Save"):
                if nama and nom > 0:
                    if simpan_pengeluaran(nama, f"[OWNER] {ket}", nom):
                        st.success("Saved!"); time.sleep(1); st.rerun()

        # --- OWNER TAB 3: PROFIT ---
        with t3:
            st.header("💵 Profit & Share")
            c1, c2 = st.columns(2)
            with c1: bln_p = st.selectbox("Profit Month", range(1, 13), index=datetime.now().month - 1, key="prof_b")
            with c2: thn_p = st.number_input("Profit Year", value=datetime.now().year, key="prof_t")
            
            if st.button("Calculate"):
                try:
                    # 1. OMSET (DARI PEMASUKAN)
                    rev = 0; disc = 0
                    sheet_in = get_google_sheet('Pemasukan'); df_in = pd.DataFrame(sheet_in.get_all_records())
                    if not df_in.empty:
                        df_in['Tanggal'] = pd.to_datetime(df_in['Tanggal'])
                        df_rev = df_in[(df_in['Tanggal'].dt.month == bln_p) & (df_in['Tanggal'].dt.year == thn_p)]
                        
                        def clean(x): 
                            try: return int(str(x).replace('.','').replace(',','').replace('Rp','').strip())
                            except: return 0
                        df_rev['Nominal'] = df_rev['Nominal'].apply(clean)
                        
                        rev = df_rev[df_rev['Nominal'] > 0]['Nominal'].sum()
                        disc = abs(df_rev[df_rev['Nominal'] < 0]['Nominal'].sum())

                    # 2. EXPENSE
                    exp = 0
                    sheet_out = get_google_sheet('Pengeluaran'); df_out = pd.DataFrame(sheet_out.get_all_records())
                    if not df_out.empty:
                        df_out['Tanggal'] = pd.to_datetime(df_out['Tanggal'])
                        df_exp = df_out[(df_out['Tanggal'].dt.month == bln_p) & (df_out['Tanggal'].dt.year == thn_p)]
                        if not df_exp.empty: exp = df_exp['Nominal'].apply(clean).sum()

                    # 3. RESULT
                    net_rev = rev - disc 
                    net_profit = net_rev - exp
                    
                    st.divider()
                    c1, c2 = st.columns(2)
                    c1.metric("Gross Revenue (Service)", f"{rev:,}".replace(',', '.'))
                    c1.metric("Discount", f"{disc:,}".replace(',', '.'), delta_color="inverse")
                    c2.metric("Net Revenue", f"{net_rev:,}".replace(',', '.'))
                    c2.metric("Expenses", f"{exp:,}".replace(',', '.'))
                    
                    st.write("---")
                    if net_profit >= 0: st.success(f"### Net Profit: Rp {net_profit:,}".replace(',', '.'))
                    else: st.error(f"### Loss: Rp {net_profit:,}".replace(',', '.'))
                    
                    st.write("---")
                    c_s1, c_s2, c_s3 = st.columns(3)
                    c_s1.info(f"**42%**: Rp {int(net_profit*0.42):,}".replace(',', '.'))
                    c_s2.warning(f"**5%**: Rp {int(net_profit*0.05):,}".replace(',', '.'))
                    c_s3.success(f"**53%**: Rp {int(net_profit*0.53):,}".replace(',', '.'))

                except Exception as e: st.error(f"Error: {e}")

    elif pass_owner: st.error("Wrong Password!")
