import streamlit as st
import pandas as pd
import datetime
from pathlib import Path
import utils 

st.set_page_config(
    page_title="Simulador de Reajuste de Arriendos",
    page_icon="🏠",
    layout="wide"
)

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            min-width: 350px; /* Ancho mínimo de la barra lateral */
            max-width: 400px; /* Ancho máximo */
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================
# BARRA LATERAL (INPUTS DE USUARIO) Y FUENTE
# ==========================================
st.sidebar.markdown(
    "<h1 style='text-align: center; font-size: 28px; color: #202124;'>🏠 ¡Bienvenido! 🎯</h1>", 
    unsafe_allow_html=True
)

st.sidebar.markdown(f"""
    <div style="background-color: #e8f0fe; padding: 12px 15px; border-radius: 8px; border: 1px solid #d2e3fc; display: flex; align-items: center; gap: 12px; margin-bottom: 10px;">
        <span style="font-size: 28px; line-height: 1;">📅</span>
        <div>
            <div style="font-size: 13px; color: #174ea6; font-weight: bold;">Fecha de consulta:</div>
            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{datetime.date.today().strftime('%Y-%m-%d')}</div>
        </div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Selector de fuente
st.sidebar.markdown("<p style='font-size: 16px; font-weight: bold; color: #202124; margin-bottom: 5px;'>Fuente de Datos</p>", unsafe_allow_html=True)
modo_datos = st.sidebar.radio("", ["🌐 En Vivo (API Banco Central)", "📁 Local (Archivos CSV)"], index=0, label_visibility="collapsed")
st.sidebar.markdown("""
    <style>
        div.stRadio > label, div.stRadio label p {
            font-size: 15px !important;
        }
    </style>
""", unsafe_allow_html=True)

token_api = ""
if modo_datos == "🌐 En Vivo (API Banco Central)":
    token_api = st.secrets.get("BCCH_TOKEN", "")
    if token_api:
        st.sidebar.success("🔒 Token de la API cargado de forma segura.")
    else:
        token_api = st.sidebar.text_input("Token API Banco Central", type="password", help="Ingresa tu token de la BDE del Banco Central")

st.sidebar.markdown("---")

# Formulario unificado con valores por defecto en CLP y validaciones
with st.sidebar.form("form_contrato"):
    st.subheader("📜 Condiciones del Contrato")
    st.markdown("**¿Te gustaría saber en cuánto se podría reajustar tu arriendo?**<br>Ingresa los siguientes datos:", unsafe_allow_html=True)

    # index=1 selecciona "CLP" por defecto para que aparezca el reajuste al tiro
    moneda_contrato = st.selectbox("Moneda del Contrato", ["UF", "CLP"], index=1)

    if moneda_contrato == "UF":
        monto_base = st.number_input(
            "Canon Inicial de Arriendo (UF)", 
            min_value=5.0, 
            max_value=50.0, 
            value=15.0, 
            step=0.5,
            help="Debe estar entre 5 y 50 UF"
        )
        frecuencia_meses = 1  
    else:
        monto_base = st.number_input(
            "Canon Inicial de Arriendo (CLP)", 
            min_value=10000.0, 
            max_value=2000000.0, 
            value=500000.0, 
            step=10000.0,
            help="Debe estar entre 10.000 y 2.000.000 CLP"
        )
        frecuencia_meses = st.selectbox("Frecuencia de Reajuste (meses)", [3, 6, 12], index=1)

    fecha_inicio_val = st.date_input(
        "Fecha de Inicio del Contrato", 
        value=datetime.date(2023, 1, 31)
    )
    fecha_inicio_str = fecha_inicio_val.strftime("%Y-%m-%d")
    
    submitted = st.form_submit_button("Calcular Reajuste 🔍")

# Mensaje al final de la barra lateral
st.sidebar.markdown("---")
st.sidebar.markdown("""
    <div style='text-align: center; font-size: 12px; color: #5f6368; padding: 10px;'>
        <b>Desarrollado como TFM - Master en Data Science, Big Data & Business Analytics - UCM 🇪🇸</b><br>
        Agradecimientos especiales al cuerpo docente por su dedicación y su aporte a mi desarrollo profesional.<br>
        💡 Consultas o sugerencias a: <a href='mailto:pvidals@fen.uchile.cl'>pvidals@fen.uchile.cl</a>
    </div>
""", unsafe_allow_html=True)


# ==========================================
# CARGA DE DATOS (HÍBRIDA: LOCAL VS API)
# ==========================================
df_ipc, df_eee, df_uf, estado_fuente = utils.cargar_datos_inteligente(token_api, modo_datos)

st.sidebar.markdown("---")
st.sidebar.caption(f"**Estado:** {estado_fuente}")

# ==========================================
# INTERFAZ PRINCIPAL CON CONTROLADOR 'submitted'
# ==========================================
if not submitted:
    # Pantalla en blanco / de bienvenida inicial antes de pulsar calcular
    st.markdown("""
        <div style="background: linear-gradient(135deg, #e8f0fe 0%, #f1f3f4 100%); padding: 50px 30px; border-radius: 12px; border: 1px solid #d2e3fc; text-align: center; margin-top: 40px; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
            <h1 style='color: #174ea6; margin-bottom: 15px;'>🏠 Simulador Inteligente de Reajuste de Arriendos</h1>
            <p style='color: #5f6368; font-size: 18px; max-width: 750px; margin: 0 auto; line-height: 1.6;'>
                Modelo híbrido que combina la evolución histórica de la inflación con las expectativas del mercado recopiladas por el Banco Central.<br><br>
                <b>Por favor, ingresa los parámetros de tu contrato en el panel izquierdo y haz clic en el botón <span style='color: #174ea6;'>“Calcular Reajuste 🔍”</span> para desplegar el análisis completo.</b>
            </p>
        </div>
    """, unsafe_allow_html=True)

else:
    # Se ejecuta todo el motor de análisis y gráficos solo tras hacer clic
    col_eee = df_eee.columns[0]
    ts_ipc = df_ipc["variacion_ipc"]
    f_fecha_corte = pd.to_datetime("today").normalize()

    try:
        f_inicio_dt = utils.validar_fecha_inicio(fecha_inicio_str, f_fecha_corte)
    except Exception as e:
        st.error(f"Error en los datos ingresados: {e}")
        st.stop()

    if f_fecha_corte.day >= 8:
        ultimo_ipc_disponible = (f_fecha_corte - pd.DateOffset(months=1)).replace(day=1)
    else:
        ultimo_ipc_disponible = (f_fecha_corte - pd.DateOffset(months=2)).replace(day=1)

    calendario_reajustes = (
        utils.generar_calendario_clp(fecha_inicio_str, frecuencia_meses, f_fecha_corte)
        if moneda_contrato == "CLP"
        else utils.generar_calendario_uf(fecha_inicio_str, f_fecha_corte)
    )

    df_tramos_contrato, df_proy_hibrida, f_limite_efectivo = utils.calcular_historial_y_proyeccion_contrato(
        calendario_df=calendario_reajustes,
        df_ipc=df_ipc,
        df_eee=df_eee,
        ts_ipc=ts_ipc,
        f_corte=f_fecha_corte,
        f_ipc_real_limite=ultimo_ipc_disponible,
        moneda_contrato=moneda_contrato,
        col_eee=col_eee
    )

    st.markdown("""
        <h1 style='font-size: 34px; color: #202124; margin-bottom: 5px;'>
            🏡 Simulador y Proyección de Reajuste de Arriendos
        </h1>
    """, unsafe_allow_html=True)
    st.markdown("Modelo inteligente híbrido que combina la evolución histórica de la inflación con las expectativas del mercado recopiladas por el Banco Central.")

    canon_vigente_actual = float(monto_base)
    if df_tramos_contrato is not None and not df_tramos_contrato.empty:
        tramos_historicos = df_tramos_contrato[df_tramos_contrato["estado"] == "Cerrado/Real"]
        if not tramos_historicos.empty:
            for _, row in tramos_historicos.iterrows():
                ipc_t = max(0.0, float(row["ipc_total_tramo_%"]) / 100.0)
                canon_vigente_actual = round(canon_vigente_actual * (1 + ipc_t))
        else:
            canon_vigente_actual = float(monto_base)

    if not isinstance(df_uf.index, pd.DatetimeIndex):
        df_uf.index = pd.to_datetime(df_uf.index)

    df_uf_hoy = df_uf[df_uf.index == f_fecha_corte].dropna(subset=["valor_uf"])
    if not df_uf_hoy.empty:
        val_uf_hoy = float(df_uf_hoy["valor_uf"].iloc[-1])
    else:
        val_uf_hoy = float(df_uf.dropna(subset=["valor_uf"])["valor_uf"].iloc[-1]) if not df_uf.empty else 38000.0

    st.markdown("### 📋 Resumen del Contrato Ingresado")

    if moneda_contrato == "CLP":
        canon_inicial_txt = f"${monto_base:,.0f} CLP"
        canon_vigente_txt = f"${canon_vigente_actual:,.0f} CLP"
    else:
        f_inicio_dt = pd.to_datetime(fecha_inicio_str)
        val_uf_inicio = float(monto_base)  
        
        if 'df_uf' in locals() and df_uf is not None and not df_uf.empty:
            df_uf_temp = df_uf.copy()
            if not isinstance(df_uf_temp.index, pd.DatetimeIndex):
                df_uf_temp.index = pd.to_datetime(df_uf_temp.index)
                
            df_uf_inicio_sub = df_uf_temp[df_uf_temp.index <= f_inicio_dt].dropna(subset=["valor_uf"])
            if not df_uf_inicio_sub.empty:
                val_uf_inicio = float(df_uf_inicio_sub["valor_uf"].iloc[-1])

        canon_inicial_clp = monto_base * val_uf_inicio
        canon_vigente_clp = canon_vigente_actual * val_uf_hoy
        
        canon_inicial_txt = f"${canon_inicial_clp:,.0f} CLP <span style='font-size: 13px; color: #5f6368; font-weight: normal;'>({monto_base:.2f} UF)</span>"
        canon_vigente_txt = f"${canon_vigente_clp:,.0f} CLP <span style='font-size: 13px; color: #5f6368; font-weight: normal;'>({canon_vigente_actual:.2f} UF)</span>"

    frecuencia_resumen_txt = "Mensual" if moneda_contrato == "UF" else f"{frecuencia_meses} meses"

    proximo_reajuste_txt = "N/A"
    if df_tramos_contrato is not None and not df_tramos_contrato.empty:
        tramos_activos = df_tramos_contrato[df_tramos_contrato["meses_proyectados"] > 0]
        if not tramos_activos.empty:
            proximo_reajuste_txt = str(tramos_activos.iloc[0]["fin_reajuste"])
        else:
            proximo_reajuste_txt = str(df_tramos_contrato.iloc[-1]["fin_reajuste"])
            
    st.markdown(f"""
    <div style="background-color: #ffffff; padding: 25px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.02); margin-bottom: 25px;">
        <table style="width: 100%; border-collapse: collapse; font-family: sans-serif;">
            <tr style="border: none;">
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">📅</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Fecha de Inicio</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{fecha_inicio_str}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">📍</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Canon Inicial</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{canon_inicial_txt}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">💰</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Canon Vigente Actual</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{canon_vigente_txt}</div>
                        </div>
                    </div>
                </td>
            </tr>
            <tr style="border: none;">
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">💱</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Moneda del Contrato</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{moneda_contrato}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">🔄</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Frecuencia de Reajuste</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{frecuencia_resumen_txt}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 15px; width: 33%; border: none;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px; background: #f1f3f4; padding: 10px; border-radius: 8px;">⏳</span>
                        <div>
                            <div style="font-size: 11px; color: #5f6368; font-weight: 600; text-transform: uppercase;">Próximo Reajuste</div>
                            <div style="font-size: 16px; color: #202124; font-weight: bold; margin-top: 2px;">{proximo_reajuste_txt}</div>
                        </div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    res_puntual_clp = None
    df_escenarios_clp = None
    res_puntual_uf = None
    df_escenarios_uf = None

    val_opt = monto_base
    val_base = monto_base
    val_pes = monto_base

    if moneda_contrato == "CLP":
        rmse_val_clp = 2.5 
        tramos_activos = df_tramos_contrato[df_tramos_contrato["meses_proyectados"] > 0]
        
        if not tramos_activos.empty:
            tramo_actual = tramos_activos.iloc[0]
            m_meses_val = int(tramo_actual["meses_proyectados"])
            ipc_real_acum_val = float(tramo_actual["ipc_real_acum_%"])
            
            idx_actual = tramos_activos.index[0]
            canon_acum_hist = float(monto_base)
            for i in range(idx_actual):
                ipc_t = max(0.0, float(df_tramos_contrato.iloc[i]["ipc_total_tramo_%"]) / 100.0)
                canon_acum_hist = round(canon_acum_hist * (1 + ipc_t))
                
            ipc_total_estimado = float(tramo_actual["ipc_total_tramo_%"]) / 100.0
            nuevo_canon_estimado = round(canon_acum_hist * (1 + max(0.0, ipc_total_estimado)))
        else:
            m_meses_val = frecuencia_meses
            ipc_real_acum_val = 0.0
            canon_acum_hist = float(monto_base)
            nuevo_canon_estimado = float(monto_base)

        res_puntual_clp, df_escenarios_clp = utils.calcular_montecarlo_clp(
            moneda_contrato=moneda_contrato,
            monto_base=monto_base,
            f_fecha_corte=f_fecha_corte,
            df_ipc=df_ipc,
            df_tramos_contrato=df_tramos_contrato,
            m_meses_faltantes=m_meses_val,
            ipc_real_acum=ipc_real_acum_val,
            df_proy_hibrida=df_proy_hibrida,
            rmse_val=rmse_val_clp,
            canon_acumulado_historico=canon_acum_hist,
            nuevo_monto_arriendo=nuevo_canon_estimado
        )
        
        if res_puntual_clp is not None:
            val_opt = res_puntual_clp.get('optimista', nuevo_canon_estimado)
            val_base = res_puntual_clp.get('mediana', nuevo_canon_estimado)
            val_pes = res_puntual_clp.get('pesimista', nuevo_canon_estimado)
        else:
            val_base = nuevo_canon_estimado
            val_opt = nuevo_canon_estimado
            val_pes = nuevo_canon_estimado
            
    else:
        df_uf_filtrado = df_uf[df_uf.index <= f_fecha_corte].dropna(subset=["valor_uf"])
        if not df_uf_filtrado.empty:
            val_uf_periodo = float(df_uf_filtrado["valor_uf"].iloc[-1])
        else:
             val_uf_periodo = float(df_uf.dropna(subset=["valor_uf"])["valor_uf"].iloc[-1]) if not df_uf.empty else 38000.0

        df_tray_dummy = pd.DataFrame(index=df_proy_hibrida.index) if df_proy_hibrida is not None else pd.DataFrame()
        df_tray_dummy["canon_clp"] = monto_base * val_uf_periodo * 1.03

        res_puntual_uf, df_escenarios_uf, mes_obj_uf, _ = utils.calcular_montecarlo_uf(
            moneda_contrato="UF",
            monto_base=monto_base,
            f_fecha_corte=ultimo_ipc_disponible,
            df_trayectoria_mensual=df_tray_dummy,
            m_meses_faltantes=1,
            val_uf_periodo=val_uf_periodo,
            mes_eee_aplicado=f_fecha_corte,
            df_proy_hibrida=df_proy_hibrida,
            resultados_backtest={'SARIMA': {'rmse_global_pct': 2.5}},
            rmse_ganador_pct=2.5
        )
        
        if res_puntual_uf is not None:
            val_opt = res_puntual_uf['optimista']
            val_base = res_puntual_uf['mediana']
            val_pes = res_puntual_uf['pesimista']

        df_escenarios_uf = df_tramos_contrato.copy()
        df_escenarios_uf["Mes"] = df_escenarios_uf["fin_reajuste"]
        val_uf_ultimo = val_uf_periodo if val_uf_periodo > 0 else 38000
        df_escenarios_uf["Canon Base (Trayectoria)"] = monto_base * val_uf_ultimo * (1 + df_escenarios_uf["ipc_total_tramo_%"] / 100)
        df_escenarios_uf["Optimista (P10 - IPC Bajo)"] = df_escenarios_uf["Canon Base (Trayectoria)"] * 0.98
        df_escenarios_uf["Pesimista (P90 - IPC Alto)"] = df_escenarios_uf["Canon Base (Trayectoria)"] * 1.02
        df_escenarios_uf["Estado"] = df_escenarios_uf["estado"]

    opt_texto = f"${val_opt:,.0f}"
    base_texto = f"${val_base:,.0f}"
    pes_texto = f"${val_pes:,.0f}"
    etiqueta_moneda_tarjetas = "CLP"

    st.markdown("### 🎲 Escenarios probables para el próximo reajuste:")
    c_opt, c_real, c_pes = st.columns(3)

    with c_opt:
        st.markdown(f"""
            <div style="background-color: #e6f4ea; padding: 20px; border-radius: 10px; border: 1px solid #ceead6; text-align: center;">
                <span style="color: #137333; font-weight: bold; font-size: 16px;">🟢 Optimista</span><br><br>
                <span style="color: #202124; font-weight: bold; font-size: 24px;">{opt_texto}</span>
                <div style="font-size: 12px; color: #5f6368; margin-top: 5px;">{etiqueta_moneda_tarjetas}</div>
            </div>
        """, unsafe_allow_html=True)

    with c_real:
        st.markdown(f"""
            <div style="background-color: #f1f3f4; padding: 20px; border-radius: 10px; border: 1px solid #dadce0; text-align: center;">
                <span style="color: #332288; font-weight: bold; font-size: 16px;">🟣 Realista</span><br><br>
                <span style="color: #202124; font-weight: bold; font-size: 24px;">{base_texto}</span>
                <div style="font-size: 12px; color: #5f6368; margin-top: 5px;">{etiqueta_moneda_tarjetas}</div>
            </div>
        """, unsafe_allow_html=True)

    with c_pes:
        st.markdown(f"""
            <div style="background-color: #fce8e6; padding: 20px; border-radius: 10px; border: 1px solid #fad2cf; text-align: center;">
                <span style="color: #c5221f; font-weight: bold; font-size: 16px;">🔴 Pesimista</span><br><br>
                <span style="color: #202124; font-weight: bold; font-size: 24px;">{pes_texto}</span>
                <div style="font-size: 12px; color: #5f6368; margin-top: 5px;">{etiqueta_moneda_tarjetas}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("### 📈 Evolución y Proyección Sucesiva del Canon")
    if moneda_contrato == "CLP":
        fig_clp = utils.plot_plotly_interactivo_clp(
            df_tramos_contrato=df_tramos_contrato,
            fecha_inicio_contrato=fecha_inicio_str,
            monto_base=monto_base,
            nuevo_monto_arriendo=None,
            ipc_total_periodo_actual=None,
            canon_optimista=None,
            canon_pesimista=None,
            frecuencia_reajuste_meses=frecuencia_meses
        )
        if fig_clp:
            st.plotly_chart(fig_clp, use_container_width=True)
    else:
        fig_uf = utils.plot_plotly_interactivo_uf(
            df_tramos_contrato=df_tramos_contrato,
            fecha_inicio_contrato=fecha_inicio_str,
            monto_base=monto_base,
            nuevo_monto_arriendo=None,
            ipc_total_periodo_actual=None,
            df_uf=df_uf  
        )
        if fig_uf:
            st.plotly_chart(fig_uf, use_container_width=True)

    st.markdown("### 🪭 Abanico de Escenarios de Montecarlo")
    if moneda_contrato == "CLP":
        canon_base_arg = val_base if 'val_base' in locals() and val_base is not None else monto_base
        canon_opt_arg = val_opt if 'val_opt' in locals() else None
        canon_pes_arg = val_pes if 'val_pes' in locals() else None
        ipc_actual_arg = ipc_total_estimado if 'ipc_total_estimado' in locals() else None

        fig_abanico_clp = utils.plot_plotly_abanico_clp(
            df_tramos_contrato=df_tramos_contrato,
            monto_base=monto_base,
            nuevo_monto_arriendo=canon_base_arg,
            canon_optimista=canon_opt_arg,
            canon_pesimista=canon_pes_arg,
            ipc_total_periodo_actual=ipc_actual_arg,
            frecuencia_reajuste_meses=frecuencia_meses
        )
        if fig_abanico_clp:
            st.plotly_chart(fig_abanico_clp, use_container_width=True)
    else:
        if 'df_escenarios_uf' in locals() and df_escenarios_uf is not None and not df_escenarios_uf.empty:
            fig_abanico_uf = utils.plot_plotly_abanico_uf(df_escenarios_uf=df_escenarios_uf)
            if fig_abanico_uf:
                st.plotly_chart(fig_abanico_uf, use_container_width=True)

    st.markdown("### 🧐 ¿Cómo interpretar los escenarios proyectados?")
    texto_extra_opt = ""
    if moneda_contrato == "CLP":
        texto_extra_opt = "<br><span style='color: #5f6368; font-style: italic;'>(Ojo: por contrato, el canon no bajará de lo que ya pagas hoy).</span>"

    st.markdown(f"""
    <div style="background-color: #f8f9fa; padding: 18px; border-radius: 8px; border-left: 4px solid #332288; font-size: 13.5px; color: #333; line-height: 1.6; font-family: sans-serif;">
        • <b>Escenario Optimista:</b> Contexto de menor inflación o estabilidad, donde el reajuste del arriendo se desacelera. {texto_extra_opt}<br><br>
        • <b>Escenario Realista:</b> Proyección central basada en la trayectoria esperada del mercado y la frecuencia pactada.<br><br>
        • <b>Escenario Pesimista:</b> Modela un escenario de mayor presión inflacionaria por sobre la tendencia promedio.
    </div>
    """, unsafe_allow_html=True)