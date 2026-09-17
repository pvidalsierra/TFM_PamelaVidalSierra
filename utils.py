import os
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from pathlib import Path
from statsmodels.tsa.statespace.sarimax import SARIMAX
import plotly.graph_objects as go
from scipy.stats import norm
import streamlit as st
import bcchapi

# ------------------------------------------------------------------------------
#  CONEXIÓN API
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESPALDO_DIR = os.path.join(BASE_DIR, "Respaldo local")

@st.cache_data
def cargar_datos_locales():
    """
    Carga los archivos CSV desde la subcarpeta 'Respaldo local'.
    """
    try:
        path_uf = os.path.join(RESPALDO_DIR, "1. uf_historica.csv")
        path_ipc = os.path.join(RESPALDO_DIR, "2. ipc_historico.csv")
        path_eee = os.path.join(RESPALDO_DIR, "5. exp_ipc.csv")

        df_uf = pd.read_csv(path_uf, parse_dates=["fecha"], index_col="fecha").asfreq("MS")
        df_ipc = pd.read_csv(path_ipc, parse_dates=["fecha"], index_col="fecha").asfreq("MS")
        df_eee = pd.read_csv(path_eee)
        
        return df_ipc, df_eee, df_uf
    except Exception as e:
        raise FileNotFoundError(f"No se pudieron leer los CSV locales en 'Respaldo local': {e}")


def cargar_datos_en_vivo(token_api):
    """
    Descarga los datos en vivo utilizando la librería oficial bcchapi del Banco Central.
    """
    if not token_api:
        raise ValueError("Token de API vacío.")
    
    siete = bcchapi.Siete(token=token_api)
    
    # Descargamos las series principales configuradas
    # Serie UF
    df_uf = siete.cuadro(
        series=["F073.UFF.PRE.Z.D"],
        nombres=["valor_uf"]
    )
    # Aseguramos formato de fecha mensual/diario según corresponda
    df_uf.index = pd.to_datetime(df_uf.index)
    
    # Serie IPC
    df_ipc = siete.cuadro(
        series=["F074.IPC.VAR.Z.Z.C.M"],
        nombres=["variacion_ipc"]
    )
    df_ipc.index = pd.to_datetime(df_ipc.index)
    
    # Expectativas IPC (EEE)
    df_eee = siete.cuadro(
        series=["F089.IPC.VAR.24.M"],
        nombres=["exp_ipc"]
    )
    df_eee.index = pd.to_datetime(df_eee.index)
    
    return df_ipc, df_eee, df_uf

def cargar_datos_inteligente(token_api, modo_seleccionado):
    """
    Función maestra: Intenta API si está seleccionada. 
    Si no pasaste token, lo busca automáticamente en st.secrets['BCCH_TOKEN'].
    Si falla o se elige local, recurre a la carpeta 'Respaldo local'.
    """
    # Si el token viene vacío, intentamos rescatarlo desde los secretos de Streamlit
    if not token_api:
        try:
            token_api = st.secrets.get("BCCH_TOKEN", "")
        except Exception:
            token_api = ""

    df_ipc = None
    df_eee = None
    df_uf = None
    estado_fuente = "Local"

    if modo_seleccionado == "🌐 En Vivo (API Banco Central)" and token_api:
        try:
            df_ipc, df_eee, df_uf = cargar_datos_en_vivo(token_api)
            estado_fuente = "En Vivo (API Banco Central de Chile)"
        except Exception as e:
            st.warning(f"⚠️ No hay conexión con la API ({e}). Usando respaldo local...")
            df_ipc, df_eee, df_uf = cargar_datos_locales()
            estado_fuente = "Local (Por falla de API)"
    else:
        df_ipc, df_eee, df_uf = cargar_datos_locales()
        estado_fuente = "Local (Archivos CSV)"

    return df_ipc, df_eee, df_uf, estado_fuente


# ------------------------------------------------------------------------------
#  PARÁMETROS GLOBALES
# ------------------------------------------------------------------------------
SEMILLA_GLOBAL = 42 
N_SIMULACIONES = 10_000 
N_TEST = 36 

CONFIG_SARIMA = {
    'order': (1, 0, 1),             
    'seasonal_order': (1, 0, 1, 12),  
    'enforce_stationarity': False,
    'enforce_invertibility': False
}

# ------------------------------------------------------------------------------
# 1. PALETA DE COLORES PERSONALIZADA (TFM)
# ------------------------------------------------------------------------------
color_historico = "#004488"  # Azul fuerte
color_base = "#332288"       # Azul oscuro
color_optimista = "#117733"  # Verde intenso
color_pesimista = "#CC6677"  # Rosa coral
color_rango = '#88CCEE'      # Rango incertidumbre (#88CCEE en rgba es 136, 204, 238)
color_aux = "#E69F00"        # Color para mostrar proyecciones

# ==============================================================================
# FUNCIÓN PARA VERIFICAR FECHA DE INICIO DEL CONTRATO INGRESADA
# ==============================================================================

def validar_fecha_inicio(fecha_str, f_fecha_corte):
    try:
        f_inicio = pd.to_datetime(fecha_str)
    except Exception as e:
        raise ValueError(f"Formato de fecha inválido: '{fecha_str}'. Use 'YYYY-MM-DD'.")

    # ==============================================================================
    # Validar límite histórico razonable (datos desde 2000)
    # ==============================================================================
    f_corte = pd.to_datetime(f_fecha_corte)
    if f_inicio > f_corte:
        raise ValueError(f"La fecha de inicio ({fecha_str}) no puede ser posterior a hoy ({f_fecha_corte}).")
    if f_inicio < pd.to_datetime("2000-01-01"):
        raise ValueError("La fecha de inicio es demasiado antigua (mínimo 2000-01-01).")
    return f_inicio

# ==============================================================================
# PROYECCIÓN EEE
# ==============================================================================
def obtener_proyeccion_eee(eee_data, fecha_corte, col_eee):
    f_corte_dt = pd.to_datetime(fecha_corte)
    if f_corte_dt.day >= 13:
        mes_encuesta_disponible = f_corte_dt.replace(day=1)
    else:
        mes_encuesta_disponible = (f_corte_dt - pd.DateOffset(months=1)).replace(day=1)

    df_eval = eee_data.loc[:mes_encuesta_disponible]
    if df_eval.empty:
        raise ValueError(f"No hay datos de EEE disponibles a la fecha de corte {fecha_corte}.")
    
    fecha_encuesta_objetivo = f_corte_dt.replace(day=1) - pd.DateOffset(months=1)
    if fecha_encuesta_objetivo in df_eval.index:
        valor_exp = float(df_eval.loc[fecha_encuesta_objetivo, col_eee])
    else:
        val_idx = -2 if len(df_eval) >= 2 else -1
        valor_exp = float(df_eval[col_eee].iloc[val_idx])

    mes_proyectado = fecha_encuesta_objetivo + pd.DateOffset(months=1)
    return pd.DataFrame({'ipc_proyectado': [valor_exp]}, index=[mes_proyectado])

# ==============================================================================
# PROYECCIÓN SARIMA
# ==============================================================================
def proyectar_sarimax(ts_ipc_data, pasos, fecha_corte, config):
    f_corte_dt = pd.to_datetime(fecha_corte)
    ts_eval = ts_ipc_data.loc[:f_corte_dt].copy()
    if ts_eval.empty:
        raise ValueError(f"No hay datos disponibles para la fecha de corte: {fecha_corte}")

    modelo = SARIMAX(
        ts_eval,
        order=config['order'],
        seasonal_order=config['seasonal_order'],
        enforce_stationarity=config['enforce_stationarity'],
        enforce_invertibility=config['enforce_invertibility']
    )
    resultado = modelo.fit(disp=False)
    proyeccion = resultado.forecast(steps=pasos)
    proyeccion.index = pd.date_range(start=ts_eval.index[-1] + pd.offsets.MonthBegin(1), periods=pasos, freq='MS')
    proyeccion.name = 'ipc_proyectado'
    return proyeccion

# ==============================================================================
# CALENDARIOS DE REAJUSTES
# ==============================================================================
def generar_calendario_clp(fecha_inicio_contrato, frecuencia_meses, f_fecha_corte):
    f_inicio = pd.to_datetime(fecha_inicio_contrato)
    f_corte = pd.to_datetime(f_fecha_corte)
    anio, mes = f_inicio.year, f_inicio.month + 1
    if mes > 12:
        mes = 1
        anio += 1

    cursor_inicio = pd.Timestamp(year=anio, month=mes, day=1)
    calendario_clp = []

    while cursor_inicio <= f_corte:
        anio_siguiente, mes_siguiente = cursor_inicio.year, cursor_inicio.month + frecuencia_meses
        while mes_siguiente > 12:
            mes_siguiente -= 12
            anio_siguiente += 1
        inicio_siguiente = pd.Timestamp(year=anio_siguiente, month=mes_siguiente, day=1)
        fecha_fin_reajuste = inicio_siguiente - pd.DateOffset(days=1)
        calendario_clp.append({"inicio_reajuste": cursor_inicio, "fin_reajuste": fecha_fin_reajuste})
        cursor_inicio = inicio_siguiente

    if calendario_clp:
        f_base_proyeccion = calendario_clp[-1]["inicio_reajuste"]
        f_limite_final = f_base_proyeccion + pd.DateOffset(months=12)
        while cursor_inicio < f_limite_final:
            anio_siguiente, mes_siguiente = cursor_inicio.year, cursor_inicio.month + frecuencia_meses
            while mes_siguiente > 12:
                mes_siguiente -= 12
                anio_siguiente += 1
            inicio_siguiente = pd.Timestamp(year=anio_siguiente, month=mes_siguiente, day=1)
            fecha_fin_reajuste = inicio_siguiente - pd.DateOffset(days=1)
            calendario_clp.append({"inicio_reajuste": cursor_inicio, "fin_reajuste": fecha_fin_reajuste})
            cursor_inicio = inicio_siguiente

    return pd.DataFrame(calendario_clp)

def generar_calendario_uf(fecha_inicio_contrato, f_fecha_corte):
    f_inicio = pd.to_datetime(fecha_inicio_contrato)
    f_corte = pd.to_datetime(f_fecha_corte)
    f_limite_proyeccion = f_corte + pd.DateOffset(months=12)
    cursor_inicio = pd.Timestamp(year=f_inicio.year, month=f_inicio.month, day=1)
    calendario_uf = []

    while cursor_inicio <= f_limite_proyeccion:
        anio_sig, mes_sig = cursor_inicio.year, cursor_inicio.month + 1
        if mes_sig > 12:
            mes_sig = 1
            anio_sig += 1
        inicio_siguiente = pd.Timestamp(year=anio_sig, month=mes_sig, day=1)
        fecha_fin = inicio_siguiente - pd.DateOffset(days=1)
        calendario_uf.append({"inicio_reajuste": cursor_inicio, "fin_reajuste": fecha_fin})
        cursor_inicio = inicio_siguiente

    return pd.DataFrame(calendario_uf)
### CALENDARIO_REAJUSTES SE ARMA EN APP.PY

# ==============================================================================
# FUNCIÓN DE PROYECCIÓN HÍBRIDA ➔ HISTORIAL Y PROYECCIÓN DE CONTRATO (SARIMA + EEE)
# ==============================================================================
def calcular_historial_y_proyeccion_contrato(calendario_df, df_ipc, df_eee, ts_ipc, f_corte, f_ipc_real_limite, moneda_contrato, col_eee):
    resultados_tramos = []
    df_proy_hibrida = pd.DataFrame(columns=["variacion_ipc"])
    capturo_proyeccion = False

    df_ipc_nat = df_ipc.copy()
    if not isinstance(df_ipc_nat.index, pd.DatetimeIndex):
        df_ipc_nat.index = pd.to_datetime(df_ipc_nat.index)
    df_ipc_nat["variacion_ipc"] = df_ipc_nat["variacion_ipc"].astype(float)

    df_eee_nat = df_eee.copy()
    if not isinstance(df_eee_nat.index, pd.DatetimeIndex):
        df_eee_nat.index = pd.to_datetime(df_eee_nat.index)

  # ------------------------------------------------------------------------------
  # Función que permite buscar la EEE desfasada respetando la temporalidad
  # ------------------------------------------------------------------------------

    def obtener_eee_para_mes(fecha_objetivo):
        fecha_ref = fecha_objetivo - pd.DateOffset(months=1)
        match = df_eee_nat[(df_eee_nat.index.year == fecha_ref.year) & (df_eee_nat.index.month == fecha_ref.month)]
        if not match.empty:
            return float(match.iloc[0][col_eee] if col_eee in match.columns else match.iloc[0, 0])
        if fecha_ref in df_eee_nat.index:
            val = df_eee_nat.loc[fecha_ref]
            return float(val.iloc[0] if isinstance(val, pd.Series) else val)
        return None

    f_corte_dt = pd.to_datetime(f_corte)
    mes_objetivo_eee = f_corte_dt.replace(day=1) if f_corte_dt.day >= 13 else (f_corte_dt - pd.DateOffset(months=1)).replace(day=1)

    if moneda_contrato == "UF":
        f_limite_efectivo = f_corte_dt.replace(day=1) if f_corte_dt.day >= 10 else (f_corte_dt - pd.DateOffset(months=2)).replace(day=1)
    else:
        f_limite_efectivo = pd.to_datetime(f_ipc_real_limite)

    ts_ipc_corte_local = ts_ipc.loc[:f_ipc_real_limite]
    df_cuant_proy = proyectar_sarimax(ts_ipc_data=ts_ipc_corte_local, pasos=N_TEST, fecha_corte=f_ipc_real_limite, config=CONFIG_SARIMA).to_frame()
    
    if "ipc_proyectado" in df_cuant_proy.columns:
        df_cuant_proy = df_cuant_proy.rename(columns={"ipc_proyectado": "proyeccion"})

    for idx, row in calendario_df.iterrows():
        f_inicio_t = pd.to_datetime(row["inicio_reajuste"])
        f_fin_t = pd.to_datetime(row["fin_reajuste"])
        frecuencia_t = (f_fin_t.year - f_inicio_t.year) * 12 + f_fin_t.month - f_inicio_t.month + 1

        filtro_real = (df_ipc_nat.index >= f_inicio_t) & (df_ipc_nat.index <= f_fin_t) & (df_ipc_nat.index <= f_limite_efectivo)
        df_real_tramo = df_ipc_nat.loc[filtro_real]
        k_reales = len(df_real_tramo)
        m_faltantes = max(0, frecuencia_t - k_reales)

        ipc_real_acum = float(df_real_tramo["variacion_ipc"].sum()) if k_reales > 0 else 0.0
        ipc_proy_acum = 0.0
        meses_proyectados_detalle = []
        conteo_eee, conteo_cuant = 0, 0

        if m_faltantes > 0:
            inicio_proy = df_real_tramo.index[-1] + pd.DateOffset(months=1) if k_reales > 0 else f_inicio_t
            rango_faltante = pd.date_range(start=inicio_proy, periods=m_faltantes, freq="MS")

            for fecha_mes in rango_faltante:
                val_eee_mes = obtener_eee_para_mes(fecha_mes)
                if fecha_mes == mes_objetivo_eee and val_eee_mes is not None:
                    val_h = val_eee_mes
                    conteo_eee += 1
                else:
                    val_h = float(df_cuant_proy.loc[fecha_mes, "proyeccion"]) if fecha_mes in df_cuant_proy.index else float(df_cuant_proy.iloc[-1]["proyeccion"])
                    conteo_cuant += 1
                meses_proyectados_detalle.append(val_h)

            if meses_proyectados_detalle:
                ipc_proy_acum = float(pd.Series(meses_proyectados_detalle).sum())

            if not capturo_proyeccion:
                df_proy_hibrida = pd.DataFrame({"variacion_ipc": meses_proyectados_detalle}, index=rango_faltante)
                capturo_proyeccion = True

            partes_txt = []
            if conteo_eee > 0: partes_txt.append(f"{conteo_eee}m con EEE")
            if conteo_cuant > 0: partes_txt.append(f"{conteo_cuant}m con SARIMA")
            estrategia_txt = " + ".join(partes_txt)
        else:
            estrategia_txt = "Período completo con IPC real"

        resultados_tramos.append({
            "inicio_reajuste": f_inicio_t.strftime("%Y-%m-%d"),
            "fin_reajuste": f_fin_t.strftime("%Y-%m-%d"),
            "meses_reales": k_reales,
            "meses_proyectados": m_faltantes,
            "estrategia": estrategia_txt,
            "ipc_real_acum_%": round(ipc_real_acum, 4),
            "ipc_proy_acum_%": round(ipc_proy_acum, 4),
            "ipc_total_tramo_%": round(ipc_real_acum + ipc_proy_acum, 4),
            "estado": "Cerrado/Real" if m_faltantes == 0 else "En curso/Proyectado",
        })

    return pd.DataFrame(resultados_tramos), df_proy_hibrida, f_limite_efectivo



# ==============================================================================
# MONTECARLO UF
# ==============================================================================
def calcular_montecarlo_uf(moneda_contrato, monto_base, f_fecha_corte, df_trayectoria_mensual, 
                            m_meses_faltantes, val_uf_periodo, mes_eee_aplicado, df_proy_hibrida, 
                            resultados_backtest, rmse_ganador_pct):
    """
    Calcula los escenarios estocásticos de Montecarlo (puntual y trayectoria mes a mes) 
    calibrados por el RMSE del modelo, extrayendo percentiles empíricos puros para arriendos en UF.

    Parameters
    ----------
    moneda_contrato : str. Moneda en que se firmó el contrato.
    monto_base : float. Canon inicial de arriendo en UF.
    f_fecha_corte : str o pd.Timestamp. Fecha de referencia o corte.
    df_trayectoria_mensual : pd.DataFrame. DF con la evolución mensual de los cánones en CLP.
    m_meses_faltantes : int. Meses que restan para completar el tramo de reajuste.
    val_uf_periodo : float. Valor oficial de la UF al cierre del ciclo CMF (ej. 9 de abril).
    mes_eee_aplicado : str o pd.Timestamp. Mes objetivo del reajuste.
    df_proy_hibrida : pd.DataFrame. Proyecciones híbridas del IPC.
    resultados_backtest : dict. Métricas y errores de las arquitecturas evaluadas.
    rmse_ganador_pct : float o None. RMSE porcentual del modelo ganador.

    Returns
    -------
    datos_puntuales : dict or None. Diccionario con los montos en CLP para los escenarios optimista (P10), mediana (P50) y pesimista (P90) al final del tramo.
    df_trayectoria_resultado : pd.DataFrame or None. DF con la trayectoria mes a mes de los escenarios Montecarlo proyectados desde el corte en adelante.
    mes_objetivo_ts : pd.Timestamp or None. Marca de tiempo correspondiente al mes objetivo del reajuste.
    mes_inicio_proy : pd.Timestamp or None. Marca de tiempo que define el inicio formal de la proyección estocástica mes a mes.
    """

    if moneda_contrato != "UF":
        return None, None, None, None

    datos_puntuales = None
    df_trayectoria_resultado = None
    mes_objetivo_ts = None
    mes_inicio_proy = None

    # Parámetros globales
    n_simulaciones = globals().get('N_SIMULACIONES', 5000)
    semilla = globals().get('SEMILLA_GLOBAL', 42)

    # --- Cálculo 1: Montecarlo Puntual ---
    # Corregido: se evalúa la variable mes_eee_aplicado directamente sin comillas
    if m_meses_faltantes > 0 and df_proy_hibrida is not None and not df_proy_hibrida.empty and mes_eee_aplicado is not None:
        mes_objetivo_ts = pd.to_datetime(mes_eee_aplicado).to_period('M').to_timestamp()
        
        match_eee = df_trayectoria_mensual[
            (df_trayectoria_mensual.index.year == mes_objetivo_ts.year) & 
            (df_trayectoria_mensual.index.month == mes_objetivo_ts.month)
        ]
        
        canon_esperado_mc = float(match_eee.iloc[0]["canon_clp"]) if not match_eee.empty else float(monto_base)
        
        col_proy = 'variacion_ipc' if 'variacion_ipc' in df_proy_hibrida.columns else 'ipc_proyectado'
        predicciones_ganador = df_proy_hibrida[col_proy].iloc[:m_meses_faltantes].tolist()
        proj_ipc = [p / 100.0 for p in predicciones_ganador]

        np.random.seed(semilla)
        rmse_val = rmse_ganador_pct if rmse_ganador_pct is not None else resultados_backtest['SARIMA']['rmse_global_pct']
        sigma_ipc = float(rmse_val) / 100.0  # Calibración estocástica pura con el RMSE del modelo

        # Simulación matricial Montecarlo de choques de IPC
        sim_ipc_matriz = np.zeros((n_simulaciones, m_meses_faltantes))
        for i, p_dec in enumerate(proj_ipc):
            sim_ipc_matriz[:, i] = np.random.normal(loc=p_dec, scale=sigma_ipc, size=n_simulaciones)

        val_uf_inicial_mc = float(val_uf_periodo)
        factores_uf_sim_acum = np.cumprod(1 + sim_ipc_matriz, axis=1)
        canones_sim_clp = np.round(monto_base * val_uf_inicial_mc * factores_uf_sim_acum[:, -1])

        # Extracción de percentiles empíricos puros
        p10_sim = np.percentile(canones_sim_clp, 10)
        p50_sim = np.percentile(canones_sim_clp, 50)
        p90_sim = np.percentile(canones_sim_clp, 90)

        datos_puntuales = {
            "optimista": round(canon_esperado_mc + (p10_sim - p50_sim)),
            "mediana": round(canon_esperado_mc),
            "pesimista": round(canon_esperado_mc + (p90_sim - p50_sim))
        }

    # --- Cálculo 2: Trayectoria Mes a Mes ---
    if df_trayectoria_mensual is not None and not df_trayectoria_mensual.empty:
        f_corte_ts = pd.to_datetime(f_fecha_corte)
        mes_inicio_proy = (f_corte_ts.replace(day=1) + pd.DateOffset(months=1))
        
        df_futuro_mc = df_trayectoria_mensual[df_trayectoria_mensual.index >= mes_inicio_proy].copy()
        m_meses_total_proy = len(df_futuro_mc)
        
        if m_meses_total_proy > 0 and df_proy_hibrida is not None and not df_proy_hibrida.empty:
            col_proy_serie = 'variacion_ipc' if 'variacion_ipc' in df_proy_hibrida.columns else 'ipc_proyectado'
            predicciones_horizonte = df_proy_hibrida[col_proy_serie].iloc[:m_meses_total_proy].tolist()
            while len(predicciones_horizonte) < m_meses_total_proy:
                predicciones_horizonte.append(0.3)
                
            proj_ipc_serie = [p / 100.0 for p in predicciones_horizonte]
            np.random.seed(semilla)
            
            rmse_val = rmse_ganador_pct if rmse_ganador_pct is not None else resultados_backtest['SARIMA']['rmse_global_pct']
            sigma_ipc = float(rmse_val) / 100.0

            sim_ipc_matriz = np.zeros((n_simulaciones, m_meses_total_proy))
            for i, p_dec in enumerate(proj_ipc_serie):
                sim_ipc_matriz[:, i] = np.random.normal(loc=p_dec, scale=sigma_ipc, size=n_simulaciones)

            factores_acumulados_matriz = np.cumprod(1 + sim_ipc_matriz, axis=1)
            
            matriz_canones_clp = np.round(monto_base * float(val_uf_periodo) * factores_acumulados_matriz)

            # Extracción de percentiles empíricos a lo largo de toda la matriz proyectada
            p10_serie = np.percentile(matriz_canones_clp, 10, axis=0)
            p50_serie = np.percentile(matriz_canones_clp, 50, axis=0)
            p90_serie = np.percentile(matriz_canones_clp, 90, axis=0)

            canon_base_serie = df_futuro_mc["canon_clp"].values
            optimista_serie = canon_base_serie + (p10_serie - p50_serie)
            pesimista_serie = canon_base_serie + (p90_serie - p50_serie)

            df_trayectoria_resultado = pd.DataFrame({
                "Mes": df_futuro_mc.index.strftime("%Y-%m"),
                "Canon Base (Trayectoria)": canon_base_serie,
                "Optimista (P10 - IPC Bajo)": np.round(optimista_serie),
                "Mediana Montecarlo (P50)": canon_base_serie,
                "Pesimista (P90 - IPC Alto)": np.round(pesimista_serie)
            })

    return datos_puntuales, df_trayectoria_resultado, mes_objetivo_ts, mes_inicio_proy


# ==============================================================================
# FUNCIÓN ➔ GENERACIÓN DE ESCENARIOS MONTECARLO CLP (SUMA SIMPLE + DF_IPC)
# ==============================================================================
def calcular_montecarlo_clp(moneda_contrato, monto_base, f_fecha_corte, 
                            df_ipc, df_tramos_contrato, m_meses_faltantes, ipc_real_acum,
                            df_proy_hibrida, rmse_val, canon_acumulado_historico, nuevo_monto_arriendo):
    """
    Calcula los escenarios estocásticos de Montecarlo (puntual y tramos futuros) 
    mediante simulación estocástica pura y percentiles empíricos (suma simple), 
    utilizando exclusivamente df_ipc y aplicando restricciones estrictas de pisos y techos.
    """
    if moneda_contrato != "CLP":
        return None, None

    datos_puntuales_clp = None
    df_tramos_futuros_resultado = None
    canon_optimista, canon_pesimista = None, None

    # Parámetros globales de simulación
    n_simulaciones = globals().get('N_SIMULACIONES', 5000)
    semilla = globals().get('SEMILLA_GLOBAL', 42)
    np.random.seed(semilla)
    sigma_mensual = float(rmse_val) / 100.0  # Desviación estándar mensual basada en el RMSE

    # --- 1. Simulación Montecarlo Puntual (Tramo en curso) ---
    if m_meses_faltantes > 0 and df_proy_hibrida is not None and not df_proy_hibrida.empty:
        col_proy = 'variacion_ipc' if 'variacion_ipc' in df_proy_hibrida.columns else 'ipc_proyectado'
        predicciones_ganador = df_proy_hibrida[col_proy].tolist()
        proj_ipc = [p / 100.0 for p in predicciones_ganador]

        sim_ipc = np.zeros((n_simulaciones, m_meses_faltantes))
        if len(proj_ipc) == m_meses_faltantes:
            for i, p_dec in enumerate(proj_ipc):
                sim_ipc[:, i] = np.random.normal(loc=p_dec, scale=sigma_mensual, size=n_simulaciones)
        else:
            # Respaldo directo desde df_ipc usando 'variacion_ipc' si faltan proyecciones puntuales
            mu_ipc = df_ipc['variacion_ipc'].mean() / 100.0 if df_ipc is not None and not df_ipc.empty else 0.0
            sim_ipc = np.random.normal(loc=mu_ipc, scale=sigma_mensual, size=(n_simulaciones, m_meses_faltantes))

        ipc_real_acum_dec = float(ipc_real_acum) / 100.0

        # Acumulación exclusiva por SUMA SIMPLE
        ipc_acum_mensual_sim = np.cumsum(sim_ipc, axis=1)
        ipc_total_mensual_sim = ipc_real_acum_dec + ipc_acum_mensual_sim

        # Restricción económica de piso mínimo en 0% para el IPC simulado
        ipc_total_mensual_sim = np.maximum(0.0, ipc_total_mensual_sim)
        canones_sim_meses = np.round(canon_acumulado_historico * (1 + ipc_total_mensual_sim))
        trayectorias_sim = np.hstack([np.full((n_simulaciones, 1), canon_acumulado_historico), canones_sim_meses])

        canones_finales = trayectorias_sim[:, -1]
        
        # Extracción de percentiles empíricos puros
        p10_emp = np.percentile(canones_finales, 10)
        p50_emp = np.percentile(canones_finales, 50)
        p90_emp = np.percentile(canones_finales, 90)
        
        canon_esperado_mc = float(nuevo_monto_arriendo) if nuevo_monto_arriendo else float(p50_emp)
        piso_absoluto = float(canon_acumulado_historico)

        raw_optimista = canon_esperado_mc + (p10_emp - p50_emp)
        raw_pesimista = canon_esperado_mc + (p90_emp - p50_emp)
        
        # Reglas de negocio puntuales (sin caídas por debajo del histórico ni del base)
        canon_optimista = max(piso_absoluto, canon_esperado_mc, round(raw_optimista))
        canon_pesimista = max(canon_esperado_mc, round(raw_pesimista))

        datos_puntuales_clp = {
            "optimista": int(canon_optimista),
            "mediana": int(canon_esperado_mc),
            "pesimista": int(canon_pesimista)
        }

    # --- 2. Simulación Montecarlo Pura para Tramos Futuros (Suma Simple) ---
    if df_tramos_contrato is not None and not df_tramos_contrato.empty:
        df_tramos_futuros = df_tramos_contrato[
            (df_tramos_contrato["meses_proyectados"] > 0) | 
            (df_tramos_contrato["estado"] == "Tramo Proyectado (Futuro)") |
            (pd.to_datetime(df_tramos_contrato["inicio_reajuste"]) > pd.to_datetime(f_fecha_corte))
        ].copy()
        
        if df_tramos_futuros.empty:
            df_tramos_futuros = df_tramos_contrato.tail(2).copy()

        lista_clp_futuro_mc = []
        canon_base_acum = float(nuevo_monto_arriendo) if nuevo_monto_arriendo else float(monto_base)
        piso_minimo = float(canon_acumulado_historico)

        for idx, row in df_tramos_futuros.iterrows():
            if idx == df_tramos_futuros.index[0] and nuevo_monto_arriendo:
                c_base_val = float(nuevo_monto_arriendo)
            else:
                ipc_tramo_val = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
                canon_base_acum = round(canon_base_acum * (1 + ipc_tramo_val))
                c_base_val = canon_base_acum

            if idx == df_tramos_futuros.index[0]:
                c_opt_val = max(piso_minimo, c_base_val, round(canon_optimista)) if canon_optimista else c_base_val
                c_pes_val = max(c_base_val, round(canon_pesimista)) if canon_pesimista else c_base_val
            else:
                meses_tramo = int(row.get("meses_tramo", 6))
                
                # Volatilidad escalada por la raíz cuadrada del tiempo acumulado
                volatilidad_tramo = sigma_mensual * np.sqrt(max(1, meses_tramo * (idx + 1)))
                ipc_esperado_tramo = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)

                # Generación de escenarios de IPC para este tramo por distribución normal
                simulacion_ipc_tramo = np.random.normal(loc=ipc_esperado_tramo, 
                                                        scale=volatilidad_tramo, 
                                                        size=n_simulaciones)
                
                # Acumulación estricta por suma simple sobre el piso mínimo anterior
                simulacion_canones_tramo = np.round(piso_minimo * (1 + np.maximum(0.0, simulacion_ipc_tramo)))

                # Extracción de percentiles empíricos (P10, P50, P90)
                p10_tramo_emp = np.percentile(simulacion_canones_tramo, 10)
                p50_tramo_emp = np.percentile(simulacion_canones_tramo, 50)
                p90_tramo_emp = np.percentile(simulacion_canones_tramo, 90)

                # Desplazamiento respecto a la mediana empírica del tramo
                raw_opt_tramo = c_base_val + (p10_tramo_emp - p50_tramo_emp)
                raw_pes_tramo = c_base_val + (p90_tramo_emp - p50_tramo_emp)

                # Reglas de negocio para tramos futuros
                c_opt_val = max(piso_minimo, c_base_val, round(raw_opt_tramo))
                c_pes_val = max(c_base_val, round(raw_pes_tramo))

            # Actualizamos el piso mínimo para el siguiente tramo iterativo
            piso_minimo = c_base_val

            lista_clp_futuro_mc.append({
                "Período de Reajuste": f"{row['inicio_reajuste'][:7]} al {row['fin_reajuste'][:7]}",
                "Canon Base (Trayectoria)": c_base_val,
                "Optimista (P10 - IPC Bajo)": c_opt_val,
                "Mediana Montecarlo (P50)": c_base_val,
                "Pesimista (P90 - IPC Alto)": c_pes_val
            })

        df_tramos_futuros_resultado = pd.DataFrame(lista_clp_futuro_mc)

    return datos_puntuales_clp, df_tramos_futuros_resultado





# ==============================================================================
# GRÁFICOS CLP
# ==============================================================================
# --- LÍNEAS ---
def plot_plotly_interactivo_clp(df_tramos_contrato, fecha_inicio_contrato, monto_base, nuevo_monto_arriendo, ipc_total_periodo_actual, canon_optimista, canon_pesimista, frecuencia_reajuste_meses):
    if df_tramos_contrato is None or df_tramos_contrato.empty:
        return None

    f_inicio_dt = pd.to_datetime(fecha_inicio_contrato)
    periodos_x = [f_inicio_dt.strftime('%Y-%m')]
    canones_base_num = [float(monto_base)]
    estados_fila = ["Canon Inicial"]

    canon_acum_base = float(monto_base)
    encontro_actual = False

    for idx, row in df_tramos_contrato.iterrows():
        is_tramo_activo = (row["meses_proyectados"] > 0) and not encontro_actual
        
        if is_tramo_activo:
            encontro_actual = True
            ipc_tramo_val = ipc_total_periodo_actual if ipc_total_periodo_actual is not None else float(row["ipc_total_tramo_%"]) / 100.0
            ipc_tramo_val = max(0.0, ipc_tramo_val)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val = nuevo_monto_arriendo if nuevo_monto_arriendo is not None else canon_acum_base
            estado_fila = "Tramo Proyectado (Vigente)"
            
        elif row["estado"] == "Cerrado/Real":
            ipc_tramo_val = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val = canon_acum_base
            estado_fila = "Histórico Real"
            
        else:
            ipc_tramo_val = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val = canon_acum_base
            estado_fila = "Tramo Proyectado (Futuro)"

        periodos_x.append(row["fin_reajuste"][:7])
        canones_base_num.append(c_base_val)
        estados_fila.append(estado_fila)

    corte_idx = next((i for i, est in enumerate(estados_fila) if "Tramo Proyectado" in est), len(periodos_x) - 1)
    corte_idx = max(0, corte_idx - 1)

    fig = go.Figure()

    # --- 1. TRAZA HISTÓRICA (Cubre todo hasta el corte actual incluido) ---
    fig.add_trace(go.Scatter(
        x=periodos_x[:corte_idx+1], 
        y=canones_base_num[:corte_idx+1],
        mode='lines+markers+text', 
        name='Histórico',
        text=[f"${v:,.0f}" for v in canones_base_num[:corte_idx+1]],
        textposition="top center",
        line=dict(color=color_historico, width=3),
        marker=dict(size=8),
        hovertemplate="<b>Histórico</b><br>Canon: $%{y:,.0f}<extra></extra>"
    ))

    # --- 2. TRAZA DE PROYECCIÓN (Arranca un paso después para evitar colisiones de X) ---
    if corte_idx + 1 < len(periodos_x):
        x_proy = periodos_x[corte_idx:]
        y_proy = [canones_base_num[corte_idx]] + canones_base_num[corte_idx+1:]
        text_proy = [""] + [f"${v:,.0f}" for v in canones_base_num[corte_idx+1:]]

        fig.add_trace(go.Scatter(
            x=x_proy, 
            y=y_proy,
            mode='lines+markers+text', 
            name='Proyección', 
            text=text_proy,
            textposition="top center",
            line=dict(color=color_aux, width=3, dash='dash'),
            marker=dict(size=8),
            hovertemplate="<b>Proyección</b><br>Canon: $%{y:,.0f}<extra></extra>"
        ))

    ymin = min(canones_base_num) * 0.99  
    ymax = max(canones_base_num) * 1.04
    
    fig.update_layout(
        title=dict(
            text=f"<b>Evolución y Proyección Sucesiva del Canon</b><br><sup>Contrato CLP - frecuencia: {frecuencia_reajuste_meses}m</sup>",
            font=dict(size=16),
            x=0.0,
            y=0.96
        ),
        xaxis_title="Períodos de análisis", 
        yaxis_title="Canon en CLP ($)",
        height=480,
        hovermode="x unified", 
        template="plotly_white",
        margin=dict(t=90, b=50, l=60, r=40),
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="left", 
            x=0.35
        )
    )

    fig.update_yaxes(
        tickformat="$,.0f",
        range=[ymin, ymax],
        autorange=False
    )

    return fig

# --- ABANICO DE MONTECARLO ---
def plot_plotly_abanico_clp(df_tramos_contrato, monto_base, nuevo_monto_arriendo, canon_optimista, canon_pesimista, ipc_total_periodo_actual, frecuencia_reajuste_meses):
    if df_tramos_contrato is None or df_tramos_contrato.empty:
        return None

    periodos_x, canones_base_num, canones_opt_num, canones_pes_num, estados_fila = [], [], [], [], []
    canon_acum_base = float(monto_base)
    
    ratio_opt = (canon_optimista / nuevo_monto_arriendo) if (canon_optimista is not None and nuevo_monto_arriendo and nuevo_monto_arriendo > 0) else 1.0
    ratio_pes = (canon_pesimista / nuevo_monto_arriendo) if (canon_pesimista is not None and nuevo_monto_arriendo and nuevo_monto_arriendo > 0) else 1.0

    encontro_actual = False
    for idx, row in df_tramos_contrato.iterrows():
        is_tramo_activo = (row["meses_proyectados"] > 0) and not encontro_actual
        if is_tramo_activo:
            encontro_actual = True
            ipc_tramo_val = max(0.0, ipc_total_periodo_actual if ipc_total_periodo_actual is not None else float(row["ipc_total_tramo_%"]) / 100.0)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val = nuevo_monto_arriendo if nuevo_monto_arriendo is not None else canon_acum_base
            c_opt_val = round(c_base_val * ratio_opt)
            c_pes_val = round(c_base_val * ratio_pes)
            estado_fila = "Tramo Proyectado (Vigente)"
        elif row["estado"] == "Cerrado/Real":
            ipc_tramo_val = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val, c_opt_val, c_pes_val = canon_acum_base, canon_acum_base, canon_acum_base
            estado_fila = "Histórico Real"
        else:
            ipc_tramo_val = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
            canon_acum_base = round(canon_acum_base * (1 + ipc_tramo_val))
            c_base_val = canon_acum_base
            c_opt_val, c_pes_val = round(c_base_val * ratio_opt), round(c_base_val * ratio_pes)
            estado_fila = "Tramo Proyectado (Futuro)"

        periodos_x.append(row["fin_reajuste"][:7])
        canones_base_num.append(c_base_val)
        canones_opt_num.append(c_opt_val)
        canones_pes_num.append(c_pes_val)
        estados_fila.append(estado_fila)

    indices_historicos = [i for i, est in enumerate(estados_fila) if est == "Histórico Real"]
    idx_corte_visual = indices_historicos[-1] if indices_historicos else 0

    periodos_grafico = periodos_x[idx_corte_visual:]
    base_grafico = canones_base_num[idx_corte_visual:]
    opt_grafico = canones_opt_num[idx_corte_visual:]
    pes_grafico = canones_pes_num[idx_corte_visual:]
    estados_grafico = estados_fila[idx_corte_visual:]

    corte_idx = max(0, next((i for i, est in enumerate(estados_grafico) if "Proyectado" in est), 0) - 1)

    fig = go.Figure()

    # Histórico
    fig.add_trace(go.Scatter(
        x=periodos_grafico[:corte_idx+1], y=base_grafico[:corte_idx+1],
        mode='lines+markers+text', name='Último Histórico Real CLP',
        text=[f"${v:,.0f}" for v in base_grafico[:corte_idx+1]],
        textposition="top center", line=dict(color=color_historico, width=2.5)
    ))

    x_proy = periodos_grafico[corte_idx:]
    y_base_proy = base_grafico[corte_idx:]
    y_opt_proy = opt_grafico[corte_idx:]
    y_pes_proy = pes_grafico[corte_idx:]

    # Rango de Incertidumbre
    fig.add_trace(go.Scatter(
        x=x_proy + x_proy[::-1], y=y_pes_proy + y_opt_proy[::-1],
        fill='toself', fillcolor='rgba(136, 204, 238, 0.25)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip", showlegend=True, name='Rango de Incertidumbre'
    ))

    # Pesimista (P90)
    fig.add_trace(go.Scatter(
        x=x_proy, y=y_pes_proy, mode='lines+markers', name='Pesimista (P90)',
        line=dict(color=color_pesimista, width=2, dash='dash'),
        marker=dict(symbol='triangle-down', size=8)
    ))

    # Base (P50)
    fig.add_trace(go.Scatter(
        x=x_proy, y=y_base_proy, mode='lines+markers+text', name='Escenario Base (P50)',
        text=[f"${v:,.0f}" for v in y_base_proy], textposition="top center",
        line=dict(color=color_base, width=2.5, dash='dash'),
        marker=dict(symbol='square', size=8)
    ))

    # Optimista (P10)
    fig.add_trace(go.Scatter(
        x=x_proy, y=y_opt_proy, mode='lines+markers', name='Optimista (P10)',
        line=dict(color=color_optimista, width=2, dash='dash'),
        marker=dict(symbol='triangle-up', size=8)
    ))

    fig.update_layout(
        title=dict(
            text=f"<b>Evolución y escenarios de Montecarlo</b><br><sup>Contrato CLP - frecuencia: {frecuencia_reajuste_meses}m (Proyección nominal por tramos)</sup>",
            font=dict(size=16),
            x=0.0,
            y=0.96
        ),
        xaxis_title="Períodos de análisis", 
        yaxis_title="Canon en CLP ($)",
        height=520,
        hovermode="x unified", 
        template="plotly_white",
        margin=dict(t=110, b=60, l=60, r=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="#d0d0d0",
            borderwidth=1,
            font=dict(size=10)
        )
    )

    
    return fig


# ==============================================================================
# GRÁFICOS UF
# ==============================================================================
# --- LINEAS ---
def plot_plotly_interactivo_uf(df_tramos_contrato, fecha_inicio_contrato, monto_base, nuevo_monto_arriendo=None, ipc_total_periodo_actual=None, df_uf=None):
    if df_tramos_contrato is None or df_tramos_contrato.empty:
        return None

    if nuevo_monto_arriendo is None:
        nuevo_monto_arriendo = float(monto_base)

    f_inicio_dt = pd.to_datetime(fecha_inicio_contrato)
    periodos_x = [f_inicio_dt.strftime('%Y-%m')]
    
    val_inicial_uf = float(monto_base)
    canones_clp_num = []
    canones_uf_num = [val_inicial_uf]
    estados_fila = ["Canon Inicial"]

    canon_acum_uf = val_inicial_uf
    encontro_actual = False

    for idx, row in df_tramos_contrato.iterrows():
        is_tramo_activo = (row.get("meses_proyectados", 0) > 0) and not encontro_actual
        
        if is_tramo_activo:
            encontro_actual = True
            ipc_tramo_val = ipc_total_periodo_actual if ipc_total_periodo_actual is not None else float(row["ipc_total_tramo_%"]) / 100.0
            ipc_tramo_val = max(0.0, ipc_tramo_val)
            if nuevo_monto_arriendo is not None and nuevo_monto_arriendo > 0:
                canon_acum_uf = float(nuevo_monto_arriendo)
            c_uf_val = canon_acum_uf
            estado_fila = "Tramo Proyectado (Vigente)"
            
        elif row.get("estado") == "Cerrado/Real":
            c_uf_val = float(monto_base) 
            estado_fila = "Histórico Real"
            
        else:
            c_uf_val = canon_acum_uf
            estado_fila = "Tramo Proyectado (Futuro)"

        periodos_x.append(str(row["fin_reajuste"])[:7])
        canones_uf_num.append(c_uf_val)
        estados_fila.append(estado_fila)

    if len(periodos_x) > 24:
        periodos_x = periodos_x[-24:]
        canones_uf_num = canones_uf_num[-24:]
        estados_fila = estados_fila[-24:]

    # Matriz / Diccionario de UF al cierre de cada mes
    matriz_uf = {}
    ultimo_uf_val = 38000.0
    
    if df_uf is not None and not df_uf.empty:
        df_uf_m = df_uf.copy()
        if not isinstance(df_uf_m.index, pd.DatetimeIndex):
            df_uf_m.index = pd.to_datetime(df_uf_m.index)
        
        df_uf_m['AnioMes'] = df_uf_m.index.strftime('%Y-%m')
        for mes_str, grupo in df_uf_m.groupby('AnioMes'):
            val_cierre = grupo["valor_uf"].dropna()
            if not val_cierre.empty:
                matriz_uf[mes_str] = float(val_cierre.iloc[-1])
        
        todas_ufs = df_uf_m["valor_uf"].dropna()
        if not todas_ufs.empty:
            ultimo_uf_val = float(todas_ufs.iloc[-1])

    canones_clp_num = []
    for i, p_str in enumerate(periodos_x):
        uf_val = matriz_uf.get(p_str, ultimo_uf_val)
        canones_clp_num.append(canones_uf_num[i] * uf_val)

    corte_idx = next((i for i, est in enumerate(estados_fila) if "Tramo Proyectado" in est), len(periodos_x) - 1)
    corte_idx = max(0, corte_idx - 1)

    fig = go.Figure()

    # Histórico UF (convertido a CLP)
    fig.add_trace(go.Scatter(
        x=periodos_x[:corte_idx+1], y=canones_clp_num[:corte_idx+1],
        mode='lines+markers+text', 
        name='Histórico UF (CLP)',
        text=[f"${v:,.0f}" for v in canones_clp_num[:corte_idx+1]],
        textposition="top center",
        line=dict(color=color_historico, width=3),
        marker=dict(size=8),
        hovertemplate="<b>Histórico UF</b><br>Período: %{customdata[0]}<br>Canon: $%{y:,.0f} CLP<br><i>(%{customdata[1]:.2f} UF)</i><extra></extra>",
        customdata=list(zip(periodos_x[:corte_idx+1], canones_uf_num[:corte_idx+1]))
    ))

    # Proyección UF (convertido a CLP)
    fig.add_trace(go.Scatter(
        x=periodos_x[corte_idx:], y=canones_clp_num[corte_idx:],
        mode='lines+markers+text', 
        name='Proyección UF (CLP)', 
        text=[f"${v:,.0f}" for v in canones_clp_num[corte_idx:]],
        textposition="top center",
        line=dict(color=color_aux, width=3, dash='dash'),
        marker=dict(size=8),
        hovertemplate="<b>Proyección UF</b><br>Período: %{customdata[0]}<br>Canon: $%{y:,.0f} CLP<br><i>(%{customdata[1]:.2f} UF)</i><extra></extra>",
        customdata=list(zip(periodos_x[corte_idx:], canones_uf_num[corte_idx:]))
    ))

    fig.update_layout(
        title=dict(
            text="<b>Evolución y Proyección del Canon (Contrato UF a CLP)</b>",
            font=dict(size=16),
            x=0.0,
            y=0.96
        ),
        xaxis_title="Períodos de análisis", 
        yaxis_title="Canon en CLP ($)",
        height=480,
        hovermode="closest", 
        template="plotly_white",
        margin=dict(t=90, b=50, l=60, r=40),
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="left", 
            x=0.3
        )
    )

    ymin = min(canones_clp_num) * 0.95
    ymax = max(canones_clp_num) * 1.05

    fig.update_yaxes(
        tickformat=",.0f",
        range=[ymin, ymax]
    )

    return fig

# --- ABANICO ---
def plot_plotly_abanico_uf(df_escenarios_uf):
    if df_escenarios_uf is None or df_escenarios_uf.empty:
        return None
    
    df_graf_proy = df_escenarios_uf.copy()

    # Asegurar columna de fecha temporal en formato datetime para poder filtrar
    if "Mes" in df_graf_proy.columns:
        df_graf_proy["Mes_dt"] = pd.to_datetime(df_graf_proy["Mes"], errors='coerce')
    else:
        return None

    # --- FILTRADO DINÁMICO: DESDE EL ÚLTIMO REAJUSTE / CIERRE HACIA ADELANTE ---
    # 1. Buscar dinámicamente si hay filas marcadas como históricas/cerradas para hallar el último hito
    fecha_corte_graf = None
    if "Estado" in df_graf_proy.columns:
        tramos_pasados = df_graf_proy[df_graf_proy["Estado"].isin(["Cerrado/Real", "Histórico Real"])]
        if not tramos_pasados.empty:
            fecha_corte_graf = tramos_pasados["Mes_dt"].max()

    # 2. Si no hay marcas de estado, calculamos dinámicamente el cierre del mes anterior (ej. 31 de agosto de 2026)
    if pd.isna(fecha_corte_graf) or fecha_corte_graf is None:
        ref_date = pd.Timestamp.today()
        fecha_corte_graf = (ref_date.replace(day=1) - pd.Timedelta(days=1))

    # Filtrar estrictamente: solo desde la fecha del último reajuste en adelante
    df_filtrado = df_graf_proy[df_graf_proy["Mes_dt"] >= fecha_corte_graf].copy()

    # Si por formato de datos el filtro estricto dejara muy pocos puntos, tomamos los últimos 12 proyectados de respaldo
    if len(df_filtrado) >= 2:
        df_graf_proy = df_filtrado
    else:
        df_graf_proy = df_graf_proy.tail(12).copy()

    if df_graf_proy.empty:
        return None

    # Usar los strings originales limpios del mes para el eje X
    x_labels = df_graf_proy["Mes"].astype(str).tolist()
    y_base = df_graf_proy["Canon Base (Trayectoria)"].astype(float).tolist()
    
    y_opt, y_pes = [], []
    for _, row in df_graf_proy.iterrows():
        opt_val = row.get("Optimista (P10 - IPC Bajo)", row["Canon Base (Trayectoria)"])
        pes_val = row.get("Pesimista (P90 - IPC Alto)", row["Canon Base (Trayectoria)"])
        base_val = float(row["Canon Base (Trayectoria)"])
        
        y_opt.append(float(opt_val) if pd.notna(opt_val) else base_val)
        y_pes.append(float(pes_val) if pd.notna(pes_val) else base_val)

    fig = go.Figure()

    # Rango de Incertidumbre (Área sombreada)
    fig.add_trace(go.Scatter(
        x=x_labels + x_labels[::-1],
        y=y_pes + y_opt[::-1],
        fill='toself',
        fillcolor='rgba(136, 204, 238, 0.25)',
        line=dict(color='rgba(255,255,255,0)'),
        hoverinfo="skip",
        showlegend=True,
        name='Rango de Incertidumbre'
    ))

    # Escenario Pesimista (P90)
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_pes,
        mode='lines+markers',
        name='Pesimista (P90)',
        line=dict(color=color_pesimista, width=2, dash='dash'),
        marker=dict(symbol='triangle-down', size=8)
    ))

    # Escenario Base (P50)
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_base,
        mode='lines+markers+text',
        name='Escenario Base (P50)',
        text=[f"${v:,.0f}" for v in y_base],
        textposition="top center",
        line=dict(color=color_base, width=2.5, dash='dash'),
        marker=dict(symbol='square', size=8)
    ))

    # Escenario Optimista (P10)
    fig.add_trace(go.Scatter(
        x=x_labels, y=y_opt,
        mode='lines+markers',
        name='Optimista (P10)',
        line=dict(color=color_optimista, width=2, dash='dash'),
        marker=dict(symbol='triangle-up', size=8)
    ))

    fig.update_layout(
        title=dict(
            text="<b>Abanico de Escenarios de Montecarlo (Contrato UF)</b>",
            font=dict(size=16),
            x=0.0,
            y=0.96
        ),
        xaxis_title="Períodos de análisis", 
        yaxis_title="Canon en CLP ($)",
        height=500,
        hovermode="x unified", 
        template="plotly_white",
        margin=dict(t=90, b=50, l=60, r=40),
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="left", 
            x=0.2
        )
    )

    return fig