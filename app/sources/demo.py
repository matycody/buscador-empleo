"""Ofertas de ejemplo para probar la web sin conexión a ningún portal."""
from datetime import datetime, timedelta, timezone


def _d(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def fetch():
    rows = [
        ("Ayudante electricista industrial", "Metalúrgica Sur", "Almirante Brown, Buenos Aires", "Mantenimiento de tableros e instalaciones industriales. Se valora curso de electricidad industrial. Sin experiencia previa.", 1, "Computrabajo"),
        ("Ayudante electricista industrial", "Metalúrgica Sur", "Almirante Brown, Buenos Aires", "Mantenimiento de tableros e instalaciones industriales. Se valora curso de electricidad industrial.", 2, "Bumeran"),
        ("Programador Junior Python", "Soluciones Web SA", "Remoto", "Desarrollo backend en Python y SQL. Trainee o junior. Equipo en crecimiento.", 0, "LinkedIn"),
        ("Programador Junior Python", "Soluciones Web SA", "Remoto", "Desarrollo backend en Python y SQL.", 3, "Indeed"),
        ("Montador tablerista", "Tableros del Plata", "Lomas de Zamora, Buenos Aires", "Montaje de tableros de potencia y baja tensión. Lectura de planos.", 4, "ZonaJobs"),
        ("Técnico en automatismos PLC", "Automat SRL", "Quilmes, Buenos Aires", "Programación de PLC Siemens LOGO! y S7-200. Automatismos industriales.", 2, "Computrabajo"),
        ("Analista de datos Jr", "Consultora Datos", "CABA", "SQL, Python y Excel. Ciencia de datos, tableros de BI.", 5, "LinkedIn"),
        ("Desarrollador Full Stack Senior", "TechCorp", "CABA", "Más de 5 años de experiencia con JavaScript, Python y SQL. Liderazgo de equipo.", 1, "Indeed"),
        ("Gerente de mantenimiento", "Planta Norte", "Rosario, Santa Fe", "Gerencia de mantenimiento industrial. 10 años de experiencia.", 6, "Bumeran"),
        ("Soporte técnico IT", "Redes y Más", "Quilmes, Buenos Aires", "Soporte a usuarios, armado de PCs, redes básicas. Pasante o junior.", 1, "Mi Empleo"),
        ("Electricista de obra", "Constructora Delta", "Lomas de Zamora, Buenos Aires", "Instalaciones eléctricas domiciliarias y de obra. Baja tensión.", 8, "Portal Empleo"),
        ("Operario de producción", "Alimentos del Sur", "Burzaco, Buenos Aires", "Línea de producción, turnos rotativos.", 2, "Jobsora"),
    ]
    return [
        {"title": t, "company": c, "location": l, "description": d, "posted": _d(days),
         "source": s, "url": f"https://example.com/{s.lower().replace(' ', '')}/{i}"}
        for i, (t, c, l, d, days, s) in enumerate(rows)
    ]
