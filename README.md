# Trabajo de Final de Máster en Data Science, Big Data & Business Analytics - Universidad Complutense de Madrid (UCM).
<br>

Autora: **Pamela Paz Vidal Sierra**.

<br>
Link de acceso a la herramienta montada en Streamlit:
https://tfm-pvidalsierra-ucm.streamlit.app
<br>

**Descripción** <br>
Esta aplicación permite cargar datos económicos (IPC, UFCLP, USDCLP, EURCLP y expectativas de inflación, desde archivos locales o directamente desde la API del Banco Central de Chile.
<br>
Con estos datos se generan proyecciones mediante un modelo SARIMA, se construyen calendarios de reajustes en CLP y UF, y se simulan escenarios estocásticos de Montecarlo.
<br>

**Objetivo** <br>
Entregar una herramienta interactiva para visualizar y analizar la evolución de contratos indexados a la inflación.
<br>
**Principales Funciones** 
1. Carga de datos (.csv o vía API).
2. Validación de fechas: asegurar que la fecha de inicio del contrato sea válida (no se evalúan contratos futuros ni que hayan sido firmados antes del año 2001).
3. Proyecciones SARIMA: predicción de IPC a futuro con modelos estadísticos.
4. Proyecciones híbridas: se combinan datos reales de la coyuntura económica (EEE) con SARIMA.
5. Calendario de reajustes: se generan de forma automática los tramos de reajuste de CLP y UF.
6. Simulación de Montecarlo: se obtienen escenarios futuros de proyección optimista, realista y pesimista.
<br>

**Forma de  Uso** <br>
1. El primer paso es seleccionar si se quiere acceder a la información de forma virtual, conectándose a la API del Banco Central de Chile o si es preferible utilizar los archivos locales. La opción local también es útil si por alguna razón la API del Banco se desconecta y es requerido consultar la información.
   En el caso de seleccionar la opción virtual, se encuentra programada - de forma segura - la conexión mediante token. 
3. Luego, para poder visualizar las métricas y proyecciones, es necesario ingresar las condiciones del contrato de arrendamiento:
   a) Fecha de inicio del contrato: a través del calendario desplegable.
   b) Moneda del contrato: UF o CLP.
   c) Canon inicial de arriendo: monto en UF o CLP, dependiendo de la moneda. Este campo tiene un aviso de referencia del rango de montos que se pueden revisar (esto es un control más que nada).
   d) Frecuencia del reajuste en meses: frecuencia con la que se reajusta el contrato de arriendo. Si el contrato está en CLP: 3, 6 o 12 meses. Si el contrato está en UF, la UF se actualiza de forma diaria, pero por simplicidad, se programó la herramienta para que muestre todos los fines de mes. Por eso la frecuencia desaparece (no se puede seleccionar).
4. Presionar botón "Calcular Reajuste" para poder visualizar todo el análisis desarrollado. 
<br>

**Recomendación** 
Se recomienda parametrizar el siguiente contrato:<br>
- Fecha de inicio: 31/01/2023.
- Moneda: UF.
Canon Inicial: 15.

Esta parametrización entrega gráficas interesantes de ver. <br>
En el caso de contratos en CLP, el canon de arriendo nominal no puede bajar. Es decir, si la variación de IPC es negativa, el canon se queda tal cual. Por eso el gráfico de abanicos no es visualmente atractivo. <br>
Por el contrario, en UF, no existe esta restricción. Por eso se recomienda esta configuración. <br>
