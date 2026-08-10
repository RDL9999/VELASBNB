# -*- coding: utf-8 -*-
"""
Datos semilla (curados manualmente) para fuentes cuyo acceso en vivo está
bloqueado por protección anti-bots (gob.mx, MéxicoX, edX, Coursera, etc.).

Cada registro tiene enlaces oficiales verificados. El radar mezcla estos datos
con los resultados en vivo (Capacítate, Skillshop) y los marca con origen.

REGLAS ÉTICAS:
- Solo oportunidades 100% gratuitas (o con periodo de prueba gratuito).
- Solo enlaces oficiales y públicos.
- Sin inventar fechas límite ni montos.
"""

SEED_ITEMS = [
    # ------------------------------------------------------------------ BECAS
    {
        "fuente_id": "gob_becas",
        "titulo": "Beca Benito Juárez - Educación Básica",
        "tipo": "beca",
        "descripcion": "Apoyo económico del Gobierno de México para estudiantes de "
                       "preescolar, primaria y secundaria inscritos en escuelas públicas "
                       "de localidades prioritarias. Consulta la convocatoria oficial.",
        "url": "https://www.gob.mx/becasbenitojuarez",
        "categoria": "Becas",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Estar inscrito en una escuela pública de educación básica",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "gob_becas",
        "titulo": "Beca Benito Juárez - Educación Media Superior",
        "tipo": "beca",
        "descripcion": "Apoyo mensual para estudiantes de preparatoria o bachillerato "
                       "de escuelas públicas. Monto y modalidad según la convocatoria.",
        "url": "https://www.gob.mx/becasbenitojuarez",
        "categoria": "Becas",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Estudiar en una escuela pública de nivel medio superior",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "gob_becas",
        "titulo": "Beca Jóvenes Escribiendo el Futuro",
        "tipo": "beca",
        "descripcion": "Beca para estudiantes de licenciatura en instituciones públicas "
                       "de educación superior de México.",
        "url": "https://www.gob.mx/becasjovenes",
        "categoria": "Becas",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Ser estudiante de licenciatura en una institución pública",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "gob_becas",
        "titulo": "Portal de Becas del Gobierno de México",
        "tipo": "beca",
        "descripcion": "Directorio oficial de todos los programas de becas federales: "
                       "educación básica, media superior, superior y posgrado.",
        "url": "https://www.gob.mx/becas",
        "categoria": "Becas",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Varía según el programa",
        "duracion_h": None,
        "origen": "curado",
    },
    # ------------------------------------------------------------- CONCURSOS
    {
        "fuente_id": "gob_convocatorias",
        "titulo": "Convocatorias oficiales del Gobierno de México",
        "tipo": "concurso",
        "descripcion": "Directorio oficial de convocatorias abiertas: empleos públicos, "
                       "concursos, premios y programas federales. Revisión semanal.",
        "url": "https://www.gob.mx/convocatorias",
        "categoria": "Concursos",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Varía según la convocatoria",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "gob_convocatorias",
        "titulo": "Convocatorias del INE (empleo y procesos electorales)",
        "tipo": "concurso",
        "descripcion": "El Instituto Nacional Electoral publica convocatorias de empleo, "
                       "capacitadores y programas sociales con pago por participación.",
        "url": "https://www.ine.mx/",
        "categoria": "Concursos",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Ser ciudadano mexicano; varía según la convocatoria",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "gob_convocatorias",
        "titulo": "Empleo público federal (Servicio Profesional de Carrera)",
        "tipo": "empleo",
        "descripcion": "Vacantes y concursos de ingreso al servicio público federal "
                       "en México. Consulta los puestos disponibles.",
        "url": "https://www.gob.mx/convocatorias",
        "categoria": "Empleos",
        "certificado": False,
        "gratis": True,
        "pais": "México",
        "requisitos": "Cumplir perfil de la plaza; varía por puesto",
        "duracion_h": None,
        "origen": "curado",
    },
    # --------------------------------------------------------------- CURSOS
    {
        "fuente_id": "mexicox",
        "titulo": "Catálogo de cursos gratuitos MéxicoX (Gobierno de México)",
        "tipo": "curso",
        "descripcion": "Cursos masivos abiertos en línea (MOOC) gratuitos del Gobierno "
                       "de México en salud, tecnología, finanzas, idiomas y más. "
                       "Algunos otorgan constancia de participación.",
        "url": "https://mexicox.gob.mx",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "México",
        "requisitos": "Crear cuenta gratuita en la plataforma",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "mexicox",
        "titulo": "Cursos de la UNAM en MéxicoX",
        "tipo": "curso",
        "descripcion": "Cursos gratuitos de la Universidad Nacional Autónoma de México "
                       "publicados en la plataforma MéxicoX.",
        "url": "https://mexicox.gob.mx",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "México",
        "requisitos": "Crear cuenta gratuita en la plataforma",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "coursera",
        "titulo": "Learning How to Learn: Powerful mental tools",
        "tipo": "curso",
        "descripcion": "Curso gratuito (auditar) de University of California San Diego y "
                       "McMaster University. Técnicas de aprendizaje eficaces. "
                       "Certificado disponible con beca o pago.",
        "url": "https://www.coursera.org/learn/learning-how-to-learn",
        "categoria": "Desarrollo personal",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Auditar gratis; certificado requiere pago o beca",
        "duracion_h": 15,
        "origen": "curado",
    },
    {
        "fuente_id": "coursera",
        "titulo": "The Science of Well-Being",
        "tipo": "curso",
        "descripcion": "Curso gratuito de la Universidad de Yale sobre psicología "
                       "positiva y bienestar. Uno de los cursos más populares del mundo.",
        "url": "https://www.coursera.org/learn/the-science-of-well-being",
        "categoria": "Desarrollo personal",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Auditar gratis; certificado requiere pago o beca",
        "duracion_h": 19,
        "origen": "curado",
    },
    {
        "fuente_id": "coursera",
        "titulo": "Python for Everybody",
        "tipo": "curso",
        "descripcion": "Curso gratuito de programación en Python de la Universidad de "
                       "Michigan. Ideal para empezar en tecnología.",
        "url": "https://www.coursera.org/learn/python",
        "categoria": "Tecnología",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Auditar gratis; certificado requiere pago o beca",
        "duracion_h": 19,
        "origen": "curado",
    },
    {
        "fuente_id": "coursera",
        "titulo": "Cursos gratuitos en Coursera (auditoría gratuita)",
        "tipo": "curso",
        "descripcion": "Catálogo de miles de cursos que puedes auditar sin pagar, "
                       "incluidos los de Google, IBM, Yale y Stanford.",
        "url": "https://www.coursera.org/courses?query=free",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Crear cuenta gratuita en Coursera",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "edx",
        "titulo": "CS50's Introduction to Computer Science (HarvardX)",
        "tipo": "curso",
        "descripcion": "Curso gratuito de Harvard para auditar en edX. Introducción "
                       "completa a la computación y la programación.",
        "url": "https://www.edx.org/course/cs50s-introduction-to-computer-science",
        "categoria": "Tecnología",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Auditar gratis; certificado verificado requiere pago",
        "duracion_h": 144,
        "origen": "curado",
    },
    {
        "fuente_id": "edx",
        "titulo": "Cursos gratuitos en edX (auditoría gratuita)",
        "tipo": "curso",
        "descripcion": "Miles de cursos universitarios gratuitos para auditar: MIT, "
                       "Harvard, Berkeley y más universidades de todo el mundo.",
        "url": "https://www.edx.org/search?tab=course&course_type=course",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Crear cuenta gratuita en edX",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "linkedin_learning",
        "titulo": "Prueba gratuita de 1 mes en LinkedIn Learning",
        "tipo": "curso",
        "descripcion": "Acceso gratuito por 1 mes a más de 20,000 cursos profesionales "
                       "en video. Cancela cuando quieras.",
        "url": "https://www.linkedin.com/learning",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Cuenta LinkedIn; vigencia del periodo de prueba",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "linkedin_learning",
        "titulo": "Cursos gratuitos destacados de LinkedIn Learning",
        "tipo": "curso",
        "descripcion": "Cursos selectos de LinkedIn Learning disponibles sin costo "
                       "durante el periodo de prueba.",
        "url": "https://www.linkedin.com/learning",
        "categoria": "Educación",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Periodo de prueba gratuito",
        "duracion_h": None,
        "origen": "curado",
    },
    {
        "fuente_id": "skillshop",
        "titulo": "Fundamentos de marketing digital (Google Actívate)",
        "tipo": "curso",
        "descripcion": "Curso gratuito de Google para dominar el marketing digital: "
                       "SEO, redes sociales, email marketing y más.",
        "url": "https://skillshop.exceedlms.com/student/catalog/list?category_ids=7880-google-activate",
        "categoria": "Marketing",
        "certificado": True,
        "gratis": True,
        "pais": "Internacional",
        "requisitos": "Crear cuenta gratuita en Skillshop",
        "duracion_h": 40,
        "origen": "curado",
    },
]
