"""
Name and field formatters for NU DentalConnect.

Provides consistent server-side normalization and client-side formatting
for year level, campus, and other fields without corrupting ordinals or acronyms.
"""
import re
from typing import Optional


class FieldFormatter:
    """
    Handles formatting of structured fields like year level and campus.

    Key design decisions:
    - NEVER uses str.title() - it corrupts "4th Year" -> "4Th Year" and "NU" -> "Nu"
    - Uses explicit patterns for known formats
    - Preserves user intent for free-text fields
    - Provides both server-side (authoritative) and client-side (progressive enhancement) formatting
    """

    # Known year level patterns and their canonical forms
    YEAR_LEVEL_PATTERNS = [
        # "Year 1" -> "Year 1"
        (re.compile(r"(?i)^year\s*([1-5])$"), lambda m: f"Year {m.group(1)}"),
        # "1st year", "2nd year", etc. -> "Year 1", "Year 2"
        (re.compile(r"(?i)^([1-5])(?:st|nd|rd|th)\s*year$"), lambda m: f"Year {m.group(1)}"),
        # "1", "2", etc. -> "Year 1", "Year 2"
        (re.compile(r"^([1-5])$"), lambda m: f"Year {m.group(1)}"),
        # "intern" -> "Intern"
        (re.compile(r"(?i)^intern$"), lambda m: "Intern"),
    ]

    # Known campus acronyms that must stay uppercase
    CAMPUS_ACRONYMS = {"NU", "U", "PH", "USA", "UK", "EU", "WHO", "ADA", "FDI"}

    # Campus name corrections (common misspellings/abbreviations)
    CAMPUS_CORRECTIONS = {
        "national university": "National University",
        "manila": "Manila",
        "makati": "Makati",
        "laguna": "Laguna",
        "cebu": "Cebu",
        "davao": "Davao",
    }

    @classmethod
    def format_year_level(cls, value: Optional[str]) -> Optional[str]:
        """
        Normalize year level input to canonical form.

        Examples:
        - "year 3" -> "Year 3"
        - "3rd year" -> "Year 3"
        - "4th Year" -> "Year 4" (NOT "4Th Year")
        - "intern" -> "Intern"
        - "Year 5" -> "Year 5"
        - "  year 2  " -> "Year 2"

        Returns None if input is empty/None.
        Returns original value if no pattern matches (preserves user input).
        """
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        # Try each pattern
        for pattern, formatter in cls.YEAR_LEVEL_PATTERNS:
            match = pattern.match(cleaned)
            if match:
                return formatter(match)

        # No pattern matched - return cleaned but don't force title case
        # Just normalize whitespace
        return re.sub(r"\s+", " ", cleaned)

    @classmethod
    def format_campus(cls, value: Optional[str]) -> Optional[str]:
        """
        Normalize campus name with proper casing.

        Rules:
        - Known acronyms (NU, WHO, ADA, etc.) stay UPPERCASE
        - Known campus names get proper title case
        - Other words: first letter capitalized, rest lowercase
        - Preserves hyphens, slashes, parentheses

        Examples:
        - "nu" -> "NU"
        - "national university" -> "National University"
        - "nu manila" -> "NU Manila"
        - "manila campus" -> "Manila Campus"
        """
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        # Check for known corrections first (case-insensitive)
        lower = cleaned.lower()
        if lower in cls.CAMPUS_CORRECTIONS:
            return cls.CAMPUS_CORRECTIONS[lower]

        # Split by spaces and process each word
        words = re.split(r"(\s+)", cleaned)  # Keep whitespace
        result = []

        for word in words:
            if not word or word.isspace():
                result.append(word)
                continue

            upper_word = word.upper()
            if upper_word in cls.CAMPUS_ACRONYMS:
                result.append(upper_word)
            elif word[0].isalpha():
                # Capitalize first letter, lowercase rest
                result.append(word[0].upper() + word[1:].lower())
            else:
                result.append(word)

        return "".join(result)

    @classmethod
    def format_full_name(cls, value: Optional[str]) -> Optional[str]:
        """
        Format full name with proper casing.

        Does NOT use str.title() because it breaks:
        - "O'Connor" -> "O'connor" (wrong)
        - "McDonald" -> "Mcdonald" (wrong)
        - "van der Waals" -> "Van Der Waals" (wrong)

        Instead, capitalizes each word's first letter, preserves internal caps.
        """
        if not value:
            return None

        cleaned = value.strip()
        if not cleaned:
            return None

        # Split on spaces, capitalize each word's first character
        words = cleaned.split()
        formatted = []
        for word in words:
            if len(word) == 1:
                formatted.append(word.upper())
            else:
                # Capitalize first letter, preserve rest
                formatted.append(word[0].upper() + word[1:])

        return " ".join(formatted)


# Client-side formatter (mirrored in app.js for progressive enhancement)
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