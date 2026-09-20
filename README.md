# Trabajo de Final de Máster en Data Science, Big Data & Business Analytics - Universidad Complutense de Madrid (UCM).
<br>
Autora: **Pamela Paz Vidal Sierra**.
<br>
Link de acceso a la herramienta montada en Streamlit:
https://tfm-pvidalsierra-ucm.streamlit.app

<br>

**Descripción** <br>
Esta aplicación permite cargar datos económicos (IPC, UFCLP, USDCLP, EURCLP y expectativas de inflación, desde archivos locales o directamente desde la API del Banco Central de Chile.

Con estos datos se generan proyecciones mediante un modelo SARIMA, se construyen calendarios de reajustes en CLP y UF, y se simulan escenarios estocásticos de Montecarlo.

**Objetivo** <br>
Entregar una herramienta interactiva para visualizar y analizar la evolución de contratos indexados a la inflación.


**Principales Funciones** 
1. Carga de datos (.csv o vía API).
2. Validación de fechas: asegurar que la fecha de inicio del contrato sea válida (no se evalúan contratos futuros ni que hayan sido firmados antes del año 2001).
3. Proyecciones SARIMA: predicción de IPC a futuro con modelos estadísticos.
4. Proyecciones híbridas: se combinan datos reales de la coyuntura económica (EEE) con SARIMA.
5. Calendario de reajustes: se generan de forma automática los tramos de reajuste de CLP y UF.
6. Simulación de Montecarlo: se obtienen escenarios futuros de proyección optimista, realista y pesimista. 
