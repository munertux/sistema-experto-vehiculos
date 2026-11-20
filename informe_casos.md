# Batería de casos del sistema experto

Generado: 2026-11-20T05:52:43 · casos: 31 · OK: 31 · FALLA: 0 · umbral mínimo de certeza: 0,20

Cada caso se ejecuta con `ServicioDiagnostico.simular()` (el mismo ciclo de la consulta real). Las preguntas no listadas en *Respuestas* se contestan con el valor de *resto*. Fuente: `pruebas/test_casos_experto.py`; regenerar con `scripts/informe_casos.py`.

| # | Caso | Entradas | Líder (esperado) | Certeza | Nivel de atención | Preguntas (máx.) | Reglas en «¿cómo?» | Resultado |
|---|------|----------|------------------|---------|-------------------|------------------|--------------------|-----------|
| 1 | Arranque: batería descargada (sin ruido ni luces) | Área: Arranque del vehículo<br>Respuestas: P9=Sí, P25=Sí; resto: No | H1 Batería completamente descargada o sulfatada (H1) | 0,50 | Revisión próxima | 3 (4) | R01 | OK |
| 2 | Arranque: bornes sulfatados (clic rápido) | Área: Arranque del vehículo<br>Respuestas: P9=Sí, P26=Sí; resto: No | H2 Conexiones de batería flojas, sulfatadas o corroídas (H2) | 0,50 | Revisión próxima | 3 (4) | R02 | OK |
| 3 | Arranque: alternador por testigo BATERIA + P0562 (R69→R70→R72) | Área: Arranque del vehículo<br>Testigos: BATERIA<br>OBD: P0562<br>Respuestas: P9=Sí, P27=Sí, P26=Sí, P29=Sí; resto: No | H5 El alternador no está generando carga (H5) | 0,89 | Revisión prioritaria | 9 (10) | T:BATERIA, OBD:P0562, R05, R69, R70, R72 | OK |
| 4 | Antirrobo: inmovilizador (testigo + gira sin arrancar) | Área: Sistema antirrobo e inmovilizador<br>Testigos: INMOVILIZADOR<br>Respuestas: P6=Sí, P89=Sí; resto: No | H65 Llave no reconocida o falla del sistema inmovilizador (H65) | 0,85 | Revisión próxima | 2 (3) | T:INMOVILIZADOR, R65, R110 | OK |
| 5 | Motor: misfire con CHECK_ENGINE + P0300 (bujías/bobinas) | Área: Motor y desempeño<br>Testigos: CHECK_ENGINE<br>OBD: P0300<br>Respuestas: P8=Sí, P34=Sí; resto: No | H10 Bujías o bobinas de encendido defectuosas (H10) | 0,82 | Revisión próxima | 8 (10) | OBD:P0300, R10, R84, R87 | OK |
| 6 | Motor: misfire severo con Check Engine parpadeante + P0301 | Área: Motor y desempeño<br>Testigos: CHECK_ENGINE<br>OBD: P0301<br>Respuestas: P8=Sí, P34=Sí, P39=Sí; resto: No | H15 Fallo de encendido severo, con riesgo de dañar el catalizador (H15) | 0,88 | No debe seguir usándose | 14 (15) | OBD:P0301, R15, R84, R85, R86 | OK |
| 7 | Motor: mezcla rica (humo negro + ralentí inestable + P0172) | Área: Motor y desempeño<br>OBD: P0172<br>Respuestas: P8=Sí, P33=Sí, P31=Sí; resto: No | H9 Exceso de inyección de combustible (mezcla rica) (H9) | 0,82 | Revisión próxima | 11 (12) | OBD:P0172, R09, R75, R79 | OK |
| 8 | Motor: humo azul sin fugas de aceite → consumo interno (R94) | Área: Motor y desempeño<br>Respuestas: P8=Sí, P36=Sí, P69=No; resto: No | H12 Consumo anormal de aceite por desgaste de anillos o sellos (H12) | 0,80 | Revisión prioritaria | 9 (10) | R12, R94 | OK |
| 9 | Lubricación: testigo ACEITE + ruido metálico (R90→R91) | Área: Motor y desempeño<br>Testigos: ACEITE<br>Respuestas: P8=Sí, P40=Sí; resto: No | H16 Falta de lubricación adecuada del motor (H16) | 0,88 | No debe seguir usándose | 8 (9) | T:ACEITE, R16, R90, R91 | OK |
| 10 | Lubricación: presión de aceite con testigo encendido | Área: Lubricación del motor<br>Testigos: ACEITE<br>Respuestas: P7=Sí, P70=Sí; resto: No | H46 Presión insuficiente de aceite por falla en la bomba, obstrucción o desgaste interno (H46) | 0,72 | No debe seguir usándose | 2 (3) | T:ACEITE, R46 | OK |
| 11 | Temperatura: sobrecalentamiento encadenado (R95→R111) | Área: Motor y desempeño<br>Testigos: TEMPERATURA<br>Respuestas: P8=Sí, P41=Sí; resto: No | H17 Falla en el sistema de refrigeración (H17) | 0,86 | No debe seguir usándose | 9 (11) | T:TEMPERATURA, R17, R95, R111 | OK |
| 12 | Temperatura: electroventilador que no enciende | Área: Temperatura del motor<br>Testigos: TEMPERATURA<br>Respuestas: P20=Sí, P42=No, P43=Sí; resto: No | H19 Falla eléctrica del ventilador o de su relé (H19) | 0,64 | Revisión prioritaria | 3 (4) | T:TEMPERATURA, R19 | OK |
| 13 | Frenos: testigo ABS + C0035 (sensor de rueda) | Área: Frenos<br>Testigos: ABS<br>OBD: C0035<br>Respuestas: P2=Sí, P47=Sí; resto: No | H23 Falla en un sensor de velocidad de rueda o en el módulo de ABS (H23) | 0,90 | Revisión prioritaria | 2 (3) | T:ABS, OBD:C0035, R23, R103 | OK |
| 14 | Frenos: pastillas desgastadas (chirrido al frenar) | Área: Frenos<br>Respuestas: P2=Sí, P46=Sí; resto: No | H22 Pastillas de freno desgastadas (H22) | 0,50 | Revisión próxima | 4 (5) | R22 | OK |
| 15 | Frenos: pedal esponjoso con testigo FRENOS (R100→R102) | Área: Frenos<br>Testigos: FRENOS<br>Respuestas: P2=Sí, P44=Sí; resto: No | H20 Aire en el circuito hidráulico o fuga de líquido de frenos (H20) | 0,86 | No debe seguir usándose | 3 (4) | T:FRENOS, R20, R100, R102 | OK |
| 16 | Dirección: dureza al girar con testigo EPS | Área: Dirección<br>Testigos: EPS<br>Respuestas: P19=Sí, P49=Sí; resto: No | H25 Falla en el sistema de dirección asistida (hidráulica o eléctrica) (H25) | 0,68 | Revisión próxima | 2 (3) | T:EPS, R25 | OK |
| 17 | Suspensión: golpe seco en baches | Área: Suspensión<br>Respuestas: P22=Sí, P60=Sí; resto: No | H36 Amortiguadores desgastados o con fuga (H36) | 0,50 | Revisión próxima | 2 (3) | R36 | OK |
| 18 | Transmisión: embrague que patina | Área: Transmisión y tren motriz<br>Respuestas: P10=Sí, P53=Sí; resto: No | H29 Disco de embrague desgastado (H29) | 0,50 | Revisión próxima | 3 (4) | R29 | OK |
| 19 | Eléctrico: ECU con CHECK_ENGINE + U0100 | Área: Sistema eléctrico<br>Testigos: CHECK_ENGINE<br>OBD: U0100<br>Respuestas: P21=Sí, P59=Sí; resto: No | H35 Falla en el módulo de control electrónico ECU/PCM (H35) | 0,88 | Revisión prioritaria | 2 (3) | T:CHECK_ENGINE, OBD:U0100, R35, R109 | OK |
| 20 | Combustible: olor a combustible y líquido cerca del tanque | Área: Sistema de combustible<br>Respuestas: P11=Sí, P72=Sí; resto: No | H48 Fuga en las líneas, conexiones o depósito de combustible (H48) | 0,60 | No debe seguir usándose | 3 (4) | R48 | OK |
| 21 | Escape: olor de gases dentro de la cabina | Área: Sistema de escape y emisiones<br>Respuestas: P17=Sí, P77=Sí; resto: No | H53 Fuga en el múltiple de escape, tuberías o conexiones del sistema (H53) | 0,60 | No debe seguir usándose | 2 (3) | R53 | OK |
| 22 | Seguridad pasiva: testigo AIRBAG + B0001 | Área: Seguridad pasiva<br>Testigos: AIRBAG<br>OBD: B0001<br>Respuestas: P24=Sí, P68=Sí; resto: No | H44 Falla en un sensor, en el cinturón de seguridad o en el módulo de airbag (H44) | 0,94 | No debe seguir usándose | 2 (3) | T:AIRBAG, OBD:B0001, R44, R106 | OK |
| 23 | Estabilidad: testigo ESP encendido durante la conducción | Área: Control de estabilidad y tracción<br>Testigos: ESP<br>Respuestas: P3=Sí, P91=Sí; resto: No | H67 Falla en sensores de velocidad, sensor de ángulo de dirección o módulo de estabilidad (H67) | 0,69 | Revisión prioritaria | 2 (3) | T:ESP, R67 | OK |
| 24 | Negación: chirrido de correa bloquea R72 (alternador) y dispara R73 (correa) | Área: Arranque del vehículo<br>Testigos: BATERIA<br>OBD: P0562<br>Respuestas: P9=Sí, P27=Sí, P26=Sí, P29=Sí, P79=Sí; resto: No | H5 El alternador no está generando carga (H5) | 0,78 | Revisión prioritaria | 9 (10) | T:BATERIA, OBD:P0562, R05 | OK |
| 25 | Parcial: 'Probablemente sí' al clic rápido | Área: Arranque del vehículo<br>Respuestas: P9=Sí, P26=Probablemente sí; resto: No | H2 Conexiones de batería flojas, sulfatadas o corroídas (H2) | 0,25 | Revisión próxima | 4 (5) | R02 | OK |
| 26 | Parcial: 'No sé' y 'Probablemente sí' (arranque lento) | Área: Arranque del vehículo<br>Respuestas: P9=Sí, P25=No sé, P26=No sé, P27=Probablemente sí; resto: No | H3 Batería con carga insuficiente o alternador que no recarga adecuadamente (H3) | 0,25 | Revisión próxima | 6 (7) | R03 | OK |
| 27 | Sin falla: todo 'No' en Arranque | Área: Arranque del vehículo<br>Respuestas: —; resto: No | Sin falla identificada (sin falla) | — | — | 8 (9) | — | OK |
| 28 | Sin falla: todo 'No' en Frenos | Área: Frenos<br>Respuestas: —; resto: No | Sin falla identificada (sin falla) | — | — | 8 (9) | — | OK |
| 29 | Sin falla: entrada 'Sí' y todo 'Probablemente no' | Área: Arranque del vehículo<br>Respuestas: P9=Sí; resto: Probablemente no | Sin falla identificada (sin falla) | — | — | 8 (9) | — | OK |
| 30 | Sin falla: testigo BATERIA desmentido por las respuestas | Área: Arranque del vehículo<br>Testigos: BATERIA<br>Respuestas: —; resto: No | Sin falla identificada (sin falla) | — | — | 10 (11) | — | OK |
| 31 | Testigo sin síntomas: Check Engine fijo y nada más | Área: Motor y desempeño<br>Testigos: CHECK_ENGINE<br>Respuestas: P38=Sí; resto: No | H14 Anomalía registrada por el sistema de control de emisiones (H14) | 0,65 | Revisión próxima | 3 (4) | T:CHECK_ENGINE, R14 | OK |

## Camino de preguntas por caso

1. **Arranque: batería descargada (sin ruido ni luces)**: P9:Sí → P25:Sí → P26:No
2. **Arranque: bornes sulfatados (clic rápido)**: P9:Sí → P25:No → P26:Sí
3. **Arranque: alternador por testigo BATERIA + P0562 (R69→R70→R72)**: P9:Sí → P29:Sí → P27:Sí → P26:Sí → P79:No → P25:No → P28:No → P5:No → P7:No
4. **Antirrobo: inmovilizador (testigo + gira sin arrancar)**: P6:Sí → P89:Sí
5. **Motor: misfire con CHECK_ENGINE + P0300 (bujías/bobinas)**: P8:Sí → P34:Sí → P35:No → P36:No → P38:No → P39:No → P30:No → P31:No
6. **Motor: misfire severo con Check Engine parpadeante + P0301**: P8:Sí → P34:Sí → P35:No → P36:No → P38:No → P39:Sí → P30:No → P31:No → P32:No → P33:No → P37:No → P40:No → P41:No → P59:No
7. **Motor: mezcla rica (humo negro + ralentí inestable + P0172)**: P8:Sí → P33:Sí → P30:No → P73:No → P31:Sí → P32:No → P34:No → P35:No → P36:No → P37:No → P38:No
8. **Motor: humo azul sin fugas de aceite → consumo interno (R94)**: P8:Sí → P30:No → P31:No → P32:No → P33:No → P34:No → P35:No → P36:Sí → P69:No
9. **Lubricación: testigo ACEITE + ruido metálico (R90→R91)**: P8:Sí → P40:Sí → P70:No → P30:No → P31:No → P32:No → P33:No → P34:No
10. **Lubricación: presión de aceite con testigo encendido**: P7:Sí → P70:Sí
11. **Temperatura: sobrecalentamiento encadenado (R95→R111)**: P8:Sí → P41:Sí → P42:No → P30:No → P31:No → P32:No → P33:No → P34:No → P35:No
12. **Temperatura: electroventilador que no enciende**: P20:Sí → P42:No → P43:Sí
13. **Frenos: testigo ABS + C0035 (sensor de rueda)**: P2:Sí → P47:Sí
14. **Frenos: pastillas desgastadas (chirrido al frenar)**: P2:Sí → P44:No → P45:No → P46:Sí
15. **Frenos: pedal esponjoso con testigo FRENOS (R100→R102)**: P2:Sí → P44:Sí → P48:No
16. **Dirección: dureza al girar con testigo EPS**: P19:Sí → P49:Sí
17. **Suspensión: golpe seco en baches**: P22:Sí → P60:Sí
18. **Transmisión: embrague que patina**: P10:Sí → P52:No → P53:Sí
19. **Eléctrico: ECU con CHECK_ENGINE + U0100**: P21:Sí → P59:Sí
20. **Combustible: olor a combustible y líquido cerca del tanque**: P11:Sí → P71:No → P72:Sí
21. **Escape: olor de gases dentro de la cabina**: P17:Sí → P77:Sí
22. **Seguridad pasiva: testigo AIRBAG + B0001**: P24:Sí → P68:Sí
23. **Estabilidad: testigo ESP encendido durante la conducción**: P3:Sí → P91:Sí
24. **Negación: chirrido de correa bloquea R72 (alternador) y dispara R73 (correa)**: P9:Sí → P29:Sí → P27:Sí → P26:Sí → P79:Sí → P25:No → P28:No → P5:No → P7:No
25. **Parcial: 'Probablemente sí' al clic rápido**: P9:Sí → P25:No → P26:Probablemente sí → P27:No
26. **Parcial: 'No sé' y 'Probablemente sí' (arranque lento)**: P9:Sí → P25:No sé → P26:No sé → P27:Probablemente sí → P28:No → P29:No
27. **Sin falla: todo 'No' en Arranque**: P9:No → P25:No → P26:No → P27:No → P28:No → P29:No → P5:No → P7:No
28. **Sin falla: todo 'No' en Frenos**: P2:No → P44:No → P45:No → P46:No → P47:No → P48:No → P5:No → P7:No
29. **Sin falla: entrada 'Sí' y todo 'Probablemente no'**: P9:Sí → P25:Probablemente no → P26:Probablemente no → P27:Probablemente no → P28:Probablemente no → P29:Probablemente no → P5:Probablemente no → P7:Probablemente no
30. **Sin falla: testigo BATERIA desmentido por las respuestas**: P9:No → P79:No → P29:No → P27:No → P25:No → P26:No → P28:No → P57:No → P5:No → P7:No
31. **Testigo sin síntomas: Check Engine fijo y nada más**: P8:No → P59:No → P38:Sí
