# Formatting ng year level, campus, at name. Nahirapan ako
# sa str.title() dati, kaya may sariling rules dito.
import re
from typing import Optional


# Bakit walang str.title(): nagiging 4Th Year at Nu yung
# output. Kaya explicit patterns na lang ginamit ko.
class FieldFormatter:

    # Mga pattern ng year level at yung kapalit na text.
    YEAR_LEVEL_PATTERNS = [
        (re.compile(r"(?i)^year\s*([1-5])$"), lambda m: f"Year {m.group(1)}"),
        (re.compile(r"(?i)^([1-5])(?:st|nd|rd|th)\s*year$"), lambda m: f"Year {m.group(1)}"),
        (re.compile(r"^([1-5])$"), lambda m: f"Year {m.group(1)}"),
        (re.compile(r"(?i)^intern$"), lambda m: "Intern"),
    ]

    # Mga acronym na dapat manatiling uppercase.
    CAMPUS_ACRONYMS = {"NU", "U", "PH", "USA", "UK", "EU", "WHO", "ADA", "FDI"}

    # Madalas na mali sa campus name, may tamang version na.
    CAMPUS_CORRECTIONS = {
        "national university": "National University",
        "manila": "Manila",
        "makati": "Makati",
        "laguna": "Laguna",
        "cebu": "Cebu",
        "davao": "Davao",
    }

    # Subukan isa-isa yung pattern. Pag walang tugma, ibabalik ko
    # yung input pero nilinis lang yung extra spaces.
    @classmethod
    def format_year_level(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        # 3rd year, Year 3, at 3, lahat nagiging Year 3.
        for pattern, formatter in cls.YEAR_LEVEL_PATTERNS:
            match = pattern.match(cleaned)
            if match:
                return formatter(match)

        return re.sub(r"\s+", " ", cleaned)

    # Acronyms stay uppercase, tapos title case yung ibang words.
    @classmethod
    def format_campus(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        lower = cleaned.lower()
        if lower in cls.CAMPUS_CORRECTIONS:
            return cls.CAMPUS_CORRECTIONS[lower]

        # Hinahati ko sa spaces pero kinikeep yung whitespace para
        # hindi magdikit yung words.
        words = re.split(r"(\s+)", cleaned)
        result = []

        for word in words:
            if not word or word.isspace():
                result.append(word)
                continue

            upper_word = word.upper()
            if upper_word in cls.CAMPUS_ACRONYMS:
                result.append(upper_word)
            elif word[0].isalpha():
                result.append(word[0].upper() + word[1:].lower())
            else:
                result.append(word)

        return "".join(result)

    # Unang letter lang ang pinapalaki. Yung O'Connor at McDonald
    # hindi masisira, kasi hindi ko ginamit yung title case.
    @classmethod
    def format_full_name(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        words = cleaned.split()
        formatted = []
        for word in words:
            if len(word) == 1:
                formatted.append(word.upper())
            else:
                formatted.append(word[0].upper() + word[1:])

        return " ".join(formatted)


# String ng JS code na mirror ng logic dito. Reference ko
# ito para sa app.js, hindi ito tinatawag sa Python.
CLIENT_FORMATTER_CODE = """
// Year Level formatter - mirrors server-side FieldFormatter.format_year_level
function formatYearLevel(value) {
    if (!value) return '';
    const cleaned = value.trim();
    if (!cleaned) return '';

    // Year 1-5 patterns
    const patterns = [
        { re: /^(?i)year\\s*([1-5])$/, fmt: m => 'Year ' + m[1] },
        { re: /^(?i)([1-5])(?:st|nd|rd|th)\\s*year$/, fmt: m => 'Year ' + m[1] },
        { re: /^([1-5])$/, fmt: m => 'Year ' + m[1] },
        { re: /^(?i)intern$/, fmt: () => 'Intern' },
    ];

    for (const p of patterns) {
        const m = cleaned.match(p.re);
        if (m) return p.fmt(m);
    }
    // No match - normalize whitespace only
    return cleaned.replace(/\\s+/g, ' ');
}

// Campus formatter - mirrors server-side FieldFormatter.format_campus
function formatCampus(value) {
    if (!value) return '';
    const cleaned = value.trim();
    if (!cleaned) return '';

    const corrections = {
        'national university': 'National University',
        'manila': 'Manila',
        'makati': 'Makati',
        'laguna': 'Laguna',
        'cebu': 'Cebu',
        'davao': 'Davao',
    };

    const acronyms = new Set(['NU', 'U', 'PH', 'USA', 'UK', 'EU', 'WHO', 'ADA', 'FDI']);

    const lower = cleaned.toLowerCase();
    if (corrections[lower]) return corrections[lower];

    // Split preserving whitespace
    return cleaned.split(/(\\s+)/).map(w => {
        if (!w || w.trim() === '') return w;
        const upper = w.toUpperCase();
        if (acronyms.has(upper)) return upper;
        if (/^[a-zA-Z]/.test(w)) return w[0].toUpperCase() + w.slice(1).toLowerCase();
        return w;
    }).join('');
}
"""