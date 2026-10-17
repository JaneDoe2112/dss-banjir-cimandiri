import streamlit as st
import pandas as pd
import json
import os
import folium
from streamlit_folium import st_folium

# Load geopandas secara aman jika terinstall
try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False

# ------------------------------------------------------
# 1. KONFIGURASI HALAMAN STREAMLIT
# ------------------------------------------------------
st.set_page_config(
    page_title="Flood Risk DSS - DAS Cimandiri",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("Flood Risk Decision Support System (DSS)")
st.caption("Analisis Spasial Risiko Limpasan Banjir DAS Cimandiri Berbasis Trend Sen's Slope (1995–2025 & Proyeksi Hingga 2100)")
st.markdown("---")

# ------------------------------------------------------
# 2. HELPER PEMBACA SPASIAL
# ------------------------------------------------------
def read_spatial_file(file_path_or_bytes, is_uploaded=False, filename=""):
    """Membaca file GeoJSON atau Shapefile (.shp / .zip) lalu return GeoJSON WGS84."""
    if HAS_GEOPANDAS:
        try:
            if is_uploaded:
                if filename.endswith(".zip") or filename.endswith(".shp"):
                    gdf = gpd.read_file(file_path_or_bytes)
                else:
                    file_path_or_bytes.seek(0)
                    gdf = gpd.read_file(file_path_or_bytes)
            else:
                if os.path.exists(file_path_or_bytes):
                    gdf = gpd.read_file(file_path_or_bytes)
                else:
                    return None

            if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)
            return json.loads(gdf.to_json())
        except Exception:
            pass

    if not is_uploaded and isinstance(file_path_or_bytes, str) and os.path.exists(file_path_or_bytes):
        try:
            with open(file_path_or_bytes, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    elif is_uploaded and (filename.endswith(".geojson") or filename.endswith(".json")):
        try:
            file_path_or_bytes.seek(0)
            return json.load(file_path_or_bytes)
        except Exception:
            return None
    return None

# ------------------------------------------------------
# 3. SIDEBAR NAVIGATION & PARAMETER
# ------------------------------------------------------
with st.sidebar:
    st.header("Navigasi Utama")
    menu = st.radio(
        "Pilih Halaman:",
        ["Dashboard", "Curah Hujan", "IDF Analysis", "Peta Risiko", "Tentang"]
    )
    st.markdown("---")

    st.subheader("Upload Data (CSV / Spasial)")
    rain_file = st.file_uploader("Upload CSV Curah Hujan (1995-2025)", type=["csv"])
    idf_file = st.file_uploader("Upload CSV IDF (Kala Ulang)", type=["csv"])
    geo_file = st.file_uploader("Upload Batas DAS KLHK (.geojson, .zip, .shp)", type=["geojson", "json", "zip", "shp"])
    jalur_file = st.file_uploader("Upload Jalur Sungai (.geojson, .json)", type=["geojson", "json"])

    geojson_das = None
    if geo_file is not None:
        geojson_das = read_spatial_file(geo_file, is_uploaded=True, filename=geo_file.name)

    if geojson_das is None:
        for fname in ["batas_das_klhk.shp", "batas_das_klhk.geojson", "das_cimandiri.shp", "das_cimandiri.geojson"]:
            loaded = read_spatial_file(fname)
            if loaded:
                geojson_das = loaded
                break

    selected_sub_das = "Batas DAS KLHK"

    das_prop_key = None
    if geojson_das and "features" in geojson_das and len(geojson_das["features"]) > 0:
        first_feat = geojson_das["features"][0].get("properties", {})
        possible_keys = ["NAMA_DAS", "NAMOBJ", "SUB_DAS", "Nama_DAS", "NAME", "name", "SUBDAS", "Kd_SubDAS", "KODE_DAS"]
        for k in possible_keys:
            if k in first_feat:
                das_prop_key = k
                break

    st.markdown("---")
    st.subheader("Parameter Hidrologi DAS")

    C = st.number_input(
        "Koefisien Limpasan (C)", 
        min_value=0.0, max_value=1.0, value=0.50, step=0.05, format="%.2f"
    )

    A = st.number_input(
        "Custom Luas DAS (A) dalam km²", 
        min_value=0.01, value=1831.96, step=1.0, format="%.2f",
        help="Nilai luas DAS bisa kamu sesuaikan secara manual sesuai data hitungan skripsi."
    )

    st.markdown("---")
    st.subheader("Skenario Analisis Waktu")
    skenario = st.radio(
        "Pilih Skenario Waktu:",
        ["Eksisting (1995–2025)", "Proyeksi Perubahan Iklim"]
    )

    tahun_proyeksi = st.selectbox(
        "Pilih Target Tahun Proyeksi:",
        [2030, 2040, 2050, 2060, 2070, 2080, 2090, 2100],
        index=2,
        disabled=(skenario == "Eksisting (1995–2025)")
    )

    laju_per_tahun = (1.386762 - 1.0) / 25.0

    if skenario != "Eksisting (1995–2025)":
        selisih_thn = tahun_proyeksi - 2025
        faktor_proyeksi = 1.386762 + (selisih_thn * laju_per_tahun)
        persen_kenaikan_sen = (faktor_proyeksi - 1.0) * 100.0
    else:
        faktor_proyeksi = 1.0
        persen_kenaikan_sen = 0.0

# ------------------------------------------------------
# 4. PEMBACAAN DATA TABEL & JALUR SUNGAI
# ------------------------------------------------------
rain_df = pd.read_csv(rain_file) if rain_file else None
idf_df = pd.read_csv(idf_file) if idf_file else None

geojson_jalur = None
if jalur_file is not None:
    geojson_jalur = read_spatial_file(jalur_file, is_uploaded=True, filename=jalur_file.name)

if geojson_jalur is None:
    geojson_jalur = read_spatial_file("jalur_sungai.geojson")

filtered_geojson_das = geojson_das

df_idf_proc = None
intensity_cols = []
durasi_col = None

if idf_df is not None:
    df_idf_proc = idf_df.copy()
    df_idf_proc.columns = df_idf_proc.columns.str.strip()
    durasi_col = df_idf_proc.columns[0]

    df_idf_proc[durasi_col] = df_idf_proc[durasi_col].astype(str).str.replace("jam", "", regex=False).str.strip()
    df_idf_proc[durasi_col] = pd.to_numeric(df_idf_proc[durasi_col], errors="coerce")

    for col in df_idf_proc.columns[1:]:
        df_idf_proc[col] = pd.to_numeric(df_idf_proc[col].astype(str).str.replace(",", "."), errors="coerce")

    df_idf_proc = df_idf_proc.dropna(subset=[durasi_col]).sort_values(durasi_col)
    intensity_cols = [c for c in df_idf_proc.columns if c != durasi_col]

# ------------------------------------------------------
# 5. IMPLEMENTASI LOGIKA HALAMAN
# ------------------------------------------------------

if menu == "Dashboard":
    st.header("Ringkasan Sistem")
    st.info(f"Wilayah Terpilih: **{selected_sub_das}** | Luas Acuan: **{A:.2f} km²**")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"**Koefisien Limpasan (C):** {C:.2f}")
    with col2:
        st.info(f"**Luas DAS (A):** {A:.2f} km²")
    with col3:
        if filtered_geojson_das:
            st.success(f"**Layer Spasial:** Active ({len(filtered_geojson_das['features'])} Feature KLHK)")
        else:
            st.warning("**Layer Spasial:** Belum ada data batas DAS")

    st.markdown("---")
    st.subheader("Status Data Input")
    st.write(f"- CSV Curah Hujan: {'`Uploaded`' if rain_file else '`Belum di-upload`'}")
    st.write(f"- CSV IDF (Kala Ulang): {'`Uploaded`' if idf_file else '`Belum di-upload`'}")
    st.write(f"- Batas DAS Spasial: {'`Loaded`' if filtered_geojson_das else '`Belum di-upload`'}")
    st.write(f"- Jalur Sungai: {'`Loaded`' if geojson_jalur else '`Belum di-upload`'}")

elif menu == "Curah Hujan":
    st.header("Analisis Curah Hujan Harian Maksimum (1995–2025)")
    if rain_df is not None:
        df_rain = rain_df.copy()
        df_rain.columns = df_rain.columns.str.strip()
        col_tahun, col_hujan = df_rain.columns[0], df_rain.columns[1]
        df_rain[col_tahun] = pd.to_numeric(df_rain[col_tahun], errors='coerce')
        df_rain[col_hujan] = pd.to_numeric(df_rain[col_hujan].astype(str).str.replace(",", "."), errors='coerce')
        df_rain = df_rain.dropna()

        st.subheader("Tabel Data Curah Hujan Harian Maksimum")
        st.dataframe(df_rain, use_container_width=True)
        st.subheader("Grafik Tren Curah Hujan Harian Maksimum")
        st.line_chart(df_rain.set_index(col_tahun)[col_hujan])
    else:
        st.warning("Silakan upload CSV Curah Hujan di sidebar terlebih dahulu.")

elif menu == "IDF Analysis":
    st.header("Kurva Intensity-Duration-Frequency (IDF)")

    if df_idf_proc is not None:
        st.subheader("1. Tabel Intensitas Hujan Desain Baseline Eksisting (mm/jam)")
        st.dataframe(df_idf_proc, use_container_width=True)

        col_select, _ = st.columns([2, 2])
        with col_select:
            selected_kala_ulang = st.selectbox(
                "Pilih Kala Ulang untuk Grafik Perbandingan:",
                intensity_cols,
                index=2 if len(intensity_cols) > 2 else 0
            )

        df_idf_proyeksi = df_idf_proc.copy()
        for col in intensity_cols:
            df_idf_proyeksi[col] = df_idf_proyeksi[col] * (1.386762 if skenario == "Eksisting (1995–2025)" else faktor_proyeksi)

        st.markdown("---")
        st.subheader(f"2. Tabel Intensitas Hujan Terdampak Tren Sen's Slope ({'Dampak Historis (1995-2025)' if skenario == 'Eksisting (1995–2025)' else 'Proyeksi ' + str(tahun_proyeksi)}) (mm/jam)")
        st.dataframe(df_idf_proyeksi, use_container_width=True)

        df_compare = pd.DataFrame({
            "Durasi (Jam)": df_idf_proc[durasi_col],
            f"IDF Baseline ({selected_kala_ulang})": df_idf_proc[selected_kala_ulang],
            f"IDF Dampak Sen's Slope ({selected_kala_ulang})": df_idf_proyeksi[selected_kala_ulang]
        }).set_index("Durasi (Jam)")

        st.markdown("---")
        st.subheader(f"Grafik Perbandingan Kurva IDF ({selected_kala_ulang}): Baseline vs Dampak Perubahan Iklim")
        st.line_chart(df_compare)
    else:
        st.warning("Silakan upload CSV IDF (Kala Ulang) di sidebar terlebih dahulu.")

elif menu == "Peta Risiko":
    st.header(f"Visualisasi Spasial Peta Risiko ({selected_sub_das})")

    if df_idf_proc is not None:
        durasi_list = df_idf_proc[durasi_col].unique().tolist()

        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            selected_ku = st.selectbox("Pilih Kala Ulang Simulasi:", intensity_cols, index=min(2, len(intensity_cols)-1))
        with col_k2:
            selected_durasi = st.selectbox("Pilih Durasi Hujan Simulasi:", durasi_list, index=0)
        with col_k3:
            idx_3 = 0
            for idx, d in enumerate(durasi_list):
                try:
                    if int(float(d)) == 3:
                        idx_3 = idx
                        break
                except ValueError:
                    pass
            durasi_acuan = st.selectbox("Durasi Acuan Threshold:", durasi_list, index=idx_3)

        # 1. AMBIL INTENSITAS SIMULASI DENGAN KONVERSI NUMERIK PRESISI
        row_simulasi = df_idf_proc[pd.to_numeric(df_idf_proc[durasi_col], errors='coerce') == float(selected_durasi)]
        I_baseline_simulasi = float(row_simulasi[selected_ku].values[0]) if not row_simulasi.empty else 0.0

        I_simulasi = I_baseline_simulasi * faktor_proyeksi
        Q = 0.278 * C * I_simulasi * A
        Q_base_murni = 0.278 * C * I_baseline_simulasi * A

        # 2. DETEKSI KOLOM KALA ULANG (MENCEGAH BENTROK STR 10 DAN 100)
        col_q10_list = [c for c in intensity_cols if c.strip() in ["10", "Q10", "T10", "10 Thn", "10 Tahun"] or ("10" in c and "100" not in c)]
        col_q50_list = [c for c in intensity_cols if c.strip() in ["50", "Q50", "T50", "50 Thn", "50 Tahun"] or "50" in c]

        # 3. KUNCI THRESHOLD Q10 DANK Q50 PADA C BASELINE ACUAN (C = 0.50)
        row_acuan = df_idf_proc[pd.to_numeric(df_idf_proc[durasi_col], errors='coerce') == float(durasi_acuan)]
        C_acuan = 0.50

        if not row_acuan.empty:
            I_q10_acuan = float(row_acuan[col_q10_list[0]].values[0]) if col_q10_list else I_baseline_simulasi
            I_q50_acuan = float(row_acuan[col_q50_list[0]].values[0]) if col_q50_list else I_baseline_simulasi * 1.30
        else:
            I_q10_acuan, I_q50_acuan = 0.0, 0.0

        # AMBANG BATAS DEBIT ACUAN Q10 & Q50
        Q_10_acuan = 0.278 * C_acuan * I_q10_acuan * A
        Q_50_acuan = 0.278 * C_acuan * I_q50_acuan * A

        # 4. PENENTUAN STATUS RISIKO (HANYA 3 KATEGORI: RENDAH, SEDANG, TINGGI)
        if Q <= Q_10_acuan:
            kondisi, warna_status = "RENDAH", "#28a745"   # Hijau
        elif Q <= Q_50_acuan:
            kondisi, warna_status = "SEDANG", "#ffc107"   # Kuning
        else:
            kondisi, warna_status = "TINGGI", "#dc3545"   # Merah

        with st.expander("🔍 Cek Angka Threshold vs Debit Simulasi"):
            st.write(f"- **Debit Terhitung Simulasi (Q):** `{Q:,.2f} m³/s` (C Input = {C})")
            st.write(f"- **Threshold Q10 (Acuan 3 Jam):** `{Q_10_acuan:,.2f} m³/s` (C Baseline = {C_acuan})")
            st.write(f"- **Threshold Q50 (Acuan 3 Jam):** `{Q_50_acuan:,.2f} m³/s` (C Baseline = {C_acuan})")

        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Intensitas Desain (I)", f"{I_simulasi:.2f} mm/jam", delta=f"+{persen_kenaikan_sen:.2f}%" if skenario != "Eksisting (1995–2025)" else "Baseline Murni")
        with m2:
            st.metric("Debit Limpasan (Q)", f"{Q:,.3f} m³/s".replace(",", "X").replace(".", ",").replace("X", "."), delta=f"{Q - Q_base_murni:+,.3f} m³/s" if skenario != "Eksisting (1995–2025)" else "Baseline Murni")
        with m3:
            if kondisi == "RENDAH":
                st.success(f"STATUS: RISIKO {kondisi}")
            elif kondisi == "SEDANG":
                st.warning(f"STATUS: RISIKO {kondisi}")
            else:
                st.error(f"STATUS: RISIKO {kondisi}")

        st.markdown("---")

        m = folium.Map(location=[-6.95, 106.85], zoom_start=10, tiles="OpenStreetMap")

        if filtered_geojson_das:
            layer_das = folium.FeatureGroup(name="Batas DAS KLHK", show=True)
            try:
                geo_das_layer = folium.GeoJson(
                    filtered_geojson_das,
                    style_function=lambda feature: {
                        'fillColor': warna_status,
                        'color': 'black',
                        'weight': 2,
                        'fillOpacity': 0.45
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=[das_prop_key] if das_prop_key else [],
                        aliases=['Nama Feature:'] if das_prop_key else [],
                        localize=True
                    )
                )
                geo_das_layer.add_to(layer_das)
                layer_das.add_to(m)

                bounds = geo_das_layer.get_bounds()
                if bounds and len(bounds) == 2 and None not in bounds[0] and None not in bounds[1]:
                    m.fit_bounds(bounds)

                    lat_center = (bounds[0][0] + bounds[1][0]) / 2
                    lon_center = (bounds[0][1] + bounds[1][1]) / 2

                    folium.Marker(
                        location=[lat_center, lon_center],
                        icon=folium.DivIcon(
                            html=f"""
                            <div style="background-color:white; border:2px solid {warna_status}; border-radius:6px; padding:4px 8px; font-size:11px; font-weight:bold; box-shadow:2px 2px 5px rgba(0,0,0,0.3); text-align:center; white-space:nowrap;">
                                <b>{selected_sub_das}</b><br>
                                Q = {Q:,.1f} m³/s ({kondisi})
                            </div>
                            """
                        )
                    ).add_to(m)
            except Exception as e:
                st.warning(f"Gagal merender data spasial: {e}")

        if geojson_jalur:
            layer_jalur = folium.FeatureGroup(name="Jalur Sungai Utama", show=True)
            folium.GeoJson(geojson_jalur, style_function=lambda f: {'color': '#0066cc', 'weight': 3.5}).add_to(layer_jalur)
            layer_jalur.add_to(m)

        folium.LayerControl(position="topright").add_to(m)

        st_folium(m, use_container_width=True, height=550, key="peta_klhk", returned_objects=[])
    else:
        st.warning("Hitungan debit dan peta risiko belum bisa ditampilkan. Silakan upload CSV IDF di sidebar terlebih dahulu.")

elif menu == "Tentang":
    st.header("Informasi Aplikasi & Metodologi")
    st.markdown("""
    * **Metode Analisis:** Persamaan Rasional ($Q = 0{,}278 \\cdot C \\cdot I \\cdot A$)
    * **Batas Administrasi DAS:** Resmi Kementerian Lingkungan Hidup dan Kehutanan (KLHK)
    * **Analisis Tren:** Sen's Slope & Mann-Kendall Test (1995–2025)
    """)