// Buong UI behaviour ng app. Naka-IIFE para hindi magkalat
// yung variables sa global scope.
(function () {
  'use strict';

  // Mirror ng WTForms rules sa server. Client side lang ito, kaya
  // mabilis makita yung error bago pa mag-submit.
  const VALIDATION_RULES = {

    'full_name': {
      required: true,
      minLength: 2,
      maxLength: 120,
      pattern: '^[\\w][\\w .,\'’\\-]{0,118}[\\w.]?$',
      patternMessage: 'Use letters, spaces, apostrophes, periods, or hyphens in the name.',
    },
    'email': {
      required: true,
      type: 'email',
      maxLength: 255,
    },
    'role': {
      required: true,
    },
    'phone': {
      required: false,
      maxLength: 20,

      pattern: '^\\+?[0-9](?:-?[0-9])*$',
      patternMessage: 'Enter a phone number with 7 to 15 digits, no more than 20 characters, using only numbers and hyphens (with + only at the start).',
      custom: function(value) {
        if (!value) return true;
        const digits = value.replace(/\D/g, '');
        return digits.length >= 7 && digits.length <= 15;
      },
      customMessage: 'Enter a phone number with 7 to 15 digits, no more than 20 characters, using only numbers and hyphens (with + only at the start).',
    },
    'password': {
      required: true,
      minLength: 12,
      maxLength: 128,
      custom: function(value) {
        return /[a-z]/.test(value) && /[A-Z]/.test(value) && /\d/.test(value);
      },
      customMessage: 'Use at least one uppercase letter, one lowercase letter, and one number.',
    },
    'confirm': {
      required: true,
      maxLength: 128,
    },

    'year_level': {
      required: false,
      maxLength: 80,
    },
    'campus': {
      required: false,
      maxLength: 120,
      pattern: '^[\\w .,\'’()\\-/]*$',
      patternMessage: 'Enter a valid campus name.',
    },
    'facebook_url': {
      required: false,
      maxLength: 255,
      custom: function(value) {
        if (!value) return true;
        try {
          const url = new URL(value);
          if (url.protocol !== 'https:') return false;
          const host = url.hostname.toLowerCase();
          if (!['facebook.com', 'www.facebook.com', 'm.facebook.com'].includes(host)) return false;
          if (!url.pathname || url.pathname === '/') return false;
          return true;
        } catch (e) {
          return false;
        }
      },
      customMessage: 'Enter a full https://www.facebook.com/ profile or page URL.',
    },
    'bio': {
      required: false,
      maxLength: 500,
    },

    'title': {
      required: true,
      minLength: 3,
      maxLength: 50,
    },
    'category': {
      required: true,
      minLength: 2,
      maxLength: 100,
    },
    'location': {
      required: true,
      minLength: 3,
      maxLength: 180,
      pattern: '^[\\w .,\'’()\\-/#]*$',
      patternMessage: 'Enter a plain-text location.',
    },
    'preferred_schedule': {
      required: true,
      minLength: 3,
      maxLength: 180,
    },
    'description': {
      required: true,
      minLength: 20,
      maxLength: 5000,
    },
    'eligibility': {
      required: true,
      minLength: 5,
      maxLength: 2000,
    },

    'message': {
      required: false,
      maxLength: 1000,
    },

    'starts_at': {
      required: true,
      type: 'datetime-local',
    },
    'proposed_at': {
      required: true,
      type: 'datetime-local',
    },
    'note': {
      required: false,
      maxLength: 1000,
    },

    'code': {
      required: true,
      pattern: '^\\d{6}$',
      patternMessage: 'Enter the six-digit code from your email.',
      minLength: 6,
      maxLength: 6,
    },

    'current_password': {
      required: true,
      maxLength: 128,
    },
  };

  // Helper: mag-set ng attribute kung wala pa, para hindi
  // ma-override yung nasa template.
  function setAttr(el, name, value) {
    if (!el.hasAttribute(name)) {
      el.setAttribute(name, value);
    }
  }

  // Helper para sa data- attribute.
  function setData(el, name, value) {
    setAttr(el, 'data-' + name, value);
  }

  // Lalagyan ng required, pattern, at type yung input base sa
  // rules, tapos novalidate yung form para sariling error ang gamit.
  function enhanceField(input, rules) {
    if (!input || !rules) return;

    const { required, minLength, maxLength, pattern, patternMessage, type, custom, customMessage } = rules;

    if (required && !input.hasAttribute('required')) {
      input.required = true;
    }
    if (minLength !== undefined) {
      setAttr(input, 'minlength', minLength);
    }
    if (maxLength !== undefined) {
      setAttr(input, 'maxlength', maxLength);
    }
    if (pattern && !input.hasAttribute('pattern')) {
      input.setAttribute('pattern', pattern);
    }
    if (patternMessage) {
      setData(input, 'pattern-message', patternMessage);
    }
    if (type && !input.hasAttribute('type')) {
      if (['email', 'url', 'tel', 'datetime-local'].includes(type)) {
        input.setAttribute('type', type);
      }
    }
    if (custom) {
      setData(input, 'custom-validate', 'true');
    }
    if (customMessage) {
      setData(input, 'custom-message', customMessage);
    }

    const form = input.closest('form');
    if (form && !form.hasAttribute('novalidate')) {
      form.setAttribute('novalidate', '');
    }
  }

  // Confirm password at confirm email: dapat pareho sa target field.
  function enhanceEqualTo(input, targetId) {
    const target = document.getElementById(targetId);
    if (target) {
      setData(input, 'equalto', targetId);
      setData(input, 'equalto-message', 'Values do not match.');
    }
  }

  // Isang span na .field-error lang, may role=alert para sa
  // screen reader, tapos is-invalid yung input.
  function showFieldError(input, message) {
    clearFieldError(input);

    input.classList.add('is-invalid');
    input.setAttribute('aria-invalid', 'true');

    const errorEl = document.createElement('span');
    errorEl.className = 'field-error';
    errorEl.textContent = message;
    errorEl.setAttribute('role', 'alert');

    const wrapper = input.closest('.field') || input.parentElement;
    wrapper.appendChild(errorEl);
  }

  // Burahin muna yung dating error para hindi dumami kada blur.
  function clearFieldError(input) {
    input.classList.remove('is-invalid');
    input.setAttribute('aria-invalid', 'false');

    const wrapper = input.closest('.field') || input.parentElement;
    const existingError = wrapper.querySelector('.field-error');
    if (existingError) {
      existingError.remove();
    }
  }

  // Isa-isang check: required, haba, pattern, custom, equalto,
  // at future date para sa datetime-local.
  function validateField(input) {
    const form = input.closest('form');
    if (!form) return true;

    let valid = true;
    let message = '';

    if (input.required && !input.value.trim()) {
      valid = false;
      message = 'This field is required.';
    }

    if (valid && input.value && input.hasAttribute('minlength')) {
      const min = parseInt(input.getAttribute('minlength'), 10);
      if (input.value.length < min) {
        valid = false;
        message = 'Must be at least ' + min + ' characters.';
      }
    }
    if (valid && input.value && input.hasAttribute('maxlength')) {
      const max = parseInt(input.getAttribute('maxlength'), 10);
      if (input.value.length > max) {
        valid = false;
        message = 'Must be no more than ' + max + ' characters.';
      }
    }

    if (valid && input.value && input.hasAttribute('pattern')) {
      const pattern = new RegExp(input.getAttribute('pattern'));
      if (!pattern.test(input.value)) {
        valid = false;
        message = input.getAttribute('data-pattern-message') || 'Invalid format.';
      }
    }

    if (valid && input.value && input.hasAttribute('data-custom-validate')) {
      const name = input.getAttribute('name');
      const rules = VALIDATION_RULES[name];
      if (rules && rules.custom && !rules.custom(input.value)) {
        valid = false;
        message = input.getAttribute('data-custom-message') || rules.customMessage || 'Invalid value.';
      }
    }

    if (valid && input.value && input.hasAttribute('data-equalto')) {
      const targetId = input.getAttribute('data-equalto');
      const target = document.getElementById(targetId) || form.querySelector('[name="' + targetId + '"]');
      if (target && input.value !== target.value) {
        valid = false;
        message = input.getAttribute('data-equalto-message') || 'Values do not match.';
      }
    }

    if (valid && input.value && input.type === 'datetime-local') {

      // Manila time ang basehan (UTC+8), hindi yung timezone ng
      // device, para pareho sa server.
      const siteNow = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 16);
      if (input.value <= siteNow) {
        valid = false;
        message = 'Choose a future date and time.';
      }
    }

    if (!valid) {
      showFieldError(input, message);
    } else {
      clearFieldError(input);
    }

    return valid;
  }

  // I-scan lahat ng form na wala pang data-enhanced, tapos
  // i-attach yung listeners. Ganito para safe sa dynamic forms.
  function enhanceAllForms() {
    const forms = document.querySelectorAll('form:not([data-enhanced="true"])');

    forms.forEach(form => {
      form.setAttribute('data-enhanced', 'true');
      form.addEventListener('submit', handleFormSubmit);

      form.querySelectorAll('input, select, textarea').forEach(input => {
        input.addEventListener('blur', () => validateField(input));
        input.addEventListener('input', () => clearFieldError(input));
      });

      const hasConfirmField = form.querySelector('[name="confirm"], [name$="_confirm"]');
      // Login form ang relaxed: walang minLength at strength check,
      // kasi may lumang password na pwedeng mas maikli.
      const isLoginForm = !hasConfirmField && form.querySelector('[name="password"]');

      const rulesForForm = isLoginForm ? { ...VALIDATION_RULES, password: { required: true, maxLength: 128 } } : VALIDATION_RULES;

      form.querySelectorAll('input[name], select[name], textarea[name]').forEach(input => {
        const name = input.getAttribute('name');
        if (rulesForForm[name]) {
          enhanceField(input, rulesForForm[name]);
        }

        if (name === 'confirm' || name.endsWith('_confirm')) {
          const targetName = name.replace('_confirm', '').replace('confirm', 'password');
          const target = form.querySelector('[name="' + targetName + '"]');
          if (target) {
            enhanceEqualTo(input, target.id || target.name);
          }
        }
      });

      form.querySelectorAll('input[type="datetime-local"]').forEach(input => {
        input.addEventListener('change', () => validateField(input));
      });
    });
  }

  // Bago mag-submit, patakbuhin lahat ng validation. Pag may
  // mali, pigilan yung submit at i-focus yung unang error.
  function handleFormSubmit(event) {
    const form = event.target;
    let allValid = true;

    form.querySelectorAll('input[required], select[required], textarea[required], input[pattern], input[data-custom-validate], input[data-equalto], input[type="datetime-local"]').forEach(input => {
      if (!validateField(input)) {
        allValid = false;
      }
    });

    if (!allValid) {
      event.preventDefault();
      event.stopPropagation();

      const firstInvalid = form.querySelector('.is-invalid');
      if (firstInvalid) {
        firstInvalid.focus();
        firstInvalid.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }

    return allValid;
  }

  // I-disable yung submit button pag nagsimula na, para hindi
  // madoble ang POST. Yung may name, hinahayaan ko kasi iba
  // yung action depende sa pinindot na button.
  document.addEventListener('submit', function (event) {
    const form = event.target;
    if (!form.matches || !form.matches('form')) return;
    const button = event.submitter || form.querySelector('button[type="submit"],button:not([type])');
    if (!button || !form.checkValidity() || button.disabled) return;
    if (button.name) return;
    button.classList.add('is-busy');
    button.setAttribute('aria-busy', 'true');
    button.disabled = true;
  });

  // Minimum date = ngayon, para hindi pumili ng nakalipas na oras.
  document.querySelectorAll('input[type="datetime-local"]').forEach(function (field) {
    if (field.min) return;

    const now = new Date(Date.now() + 8 * 60 * 60 * 1000);
    field.min = now.toISOString().slice(0, 16);
  });

  // Mobile menu. Escape at click sa labas, nagsasara. Naka-sync
  // yung aria-expanded para tama sa screen reader.
  const navToggle = document.querySelector('.nav-toggle');
  const navigation = document.querySelector('#navigation');
  if (navToggle && navigation) {
    const setNav = function (open) {
      navToggle.setAttribute('aria-expanded', String(open));
      navToggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
      navigation.classList.toggle('show', open);
      document.body.classList.toggle('nav-locked', open && window.matchMedia('(max-width: 900px)').matches);
    };

    navToggle.addEventListener('click', function () {
      setNav(navToggle.getAttribute('aria-expanded') !== 'true');
    });

    navigation.addEventListener('click', function (event) {
      if (event.target.closest('a')) setNav(false);
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      if (navToggle.getAttribute('aria-expanded') !== 'true') return;
      setNav(false);
      navToggle.focus();
    });

    document.addEventListener('click', function (event) {
      if (navToggle.getAttribute('aria-expanded') !== 'true') return;
      if (navigation.contains(event.target) || navToggle.contains(event.target)) return;
      setNav(false);
    });

    window.addEventListener('resize', function () {
      if (window.innerWidth > 1023 && navToggle.getAttribute('aria-expanded') === 'true') setNav(false);
    });
  }

  // Close button ng flash message. Tanggalin lang yung alert.
  document.querySelectorAll('.alert__close, .alert .btn-close').forEach(function (button) {
    button.addEventListener('click', function () {
      const alert = button.closest('.alert');
      if (alert) alert.remove();
    });
  });

  // Template picker sa listing editor. Yung JSON nasa script tag.
  // Pag sira yung JSON, empty list na lang ang gamit.
  const templateDataNode = document.querySelector('#listing-template-data');
  const templateChoice = document.querySelector('#template-choice');
  if (templateDataNode && templateChoice) {
    let templateData = { builtIn: [], saved: [] };
    try {
      templateData = JSON.parse(templateDataNode.textContent);
    } catch (_error) {
      templateData = { builtIn: [], saved: [] };
    }

    templateChoice.addEventListener('change', function () {
      const template = [].concat(templateData.builtIn || [], templateData.saved || [])
        .find(function (item) { return String(item.id) === templateChoice.value; });
      const feedback = document.querySelector('#template-feedback');
      if (!template) {
        if (feedback) feedback.textContent = 'Choose a template first.';
        templateChoice.focus();
        return;
      }

      const editor = document.querySelector('#listing-editor');
      const fields = ['title', 'category', 'location', 'preferred_schedule', 'description', 'eligibility'];
      const hasContent = fields.some(function (name) {
        const field = document.getElementById(name);
        return field && field.value.trim();
      });
      if (hasContent && !window.confirm('Replace the current listing fields with this template?')) return;

      fields.forEach(function (name) {
        const input = document.getElementById(name);
        if (input && Object.prototype.hasOwnProperty.call(template, name)) {
          input.value = template[name];
          input.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
      if (feedback) feedback.textContent = '“' + template.name + '” loaded. Review and edit the fields before saving.';
      const titleField = document.querySelector('#listing-editor #title');
      if (titleField) titleField.focus();
    });
  }

  // Show/hide ng password. type=button kaya hindi nag-submit, at
  // may keyboard support para sa Enter at Space.
  function initPasswordToggles() {
    document.querySelectorAll('.password-toggle').forEach(function (toggle) {
      if (toggle.hasAttribute('data-initialized')) return;
      toggle.setAttribute('data-initialized', 'true');

      const input = toggle.closest('.password-field').querySelector('input[type="password"], input[type="text"]');
      if (!input) return;

      toggle.addEventListener('click', function () {
        const isPressed = toggle.getAttribute('aria-pressed') === 'true';
        toggle.setAttribute('aria-pressed', String(!isPressed));
        toggle.setAttribute('aria-label', isPressed ? 'Show password' : 'Hide password');
        toggle.setAttribute('title', isPressed ? 'Show password' : 'Hide password');
        input.type = isPressed ? 'password' : 'text';
      });

      toggle.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle.click();
        }
      });
    });
  }

  // Student fields: hidden at disabled pag patient, para hindi
  // mapasa yung year level at campus sa server.
  function initStudentFields() {
    const roleSelect = document.querySelector('select[name="role"]');
    const details = document.querySelector('[data-student-details]');
    if (!roleSelect || !details) return;

    const fields = details.querySelectorAll('input, select, textarea');
    const sync = function () {
      const isStudent = roleSelect.value === 'student';
      details.hidden = !isStudent;
      fields.forEach(function (field) {
        field.disabled = !isStudent;
      });
    };

    roleSelect.addEventListener('change', sync);
    sync();
  }

  // Count-up animation ng stats. requestAnimationFrame para
  // smooth, tapos exact na bilang ang huling value.
  function animateCountUp(element) {
    const target = parseInt(element.dataset.target, 10) || parseInt(element.textContent.replace(/,/g, ''), 10);
    if (isNaN(target)) return;

    const duration = 1200;
    const start = performance.now();

    function update(currentTime) {
      const elapsed = currentTime - start;
      const progress = Math.min(elapsed / duration, 1);

      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.floor(target * eased);
      element.textContent = current.toLocaleString();

      if (progress < 1) {
        requestAnimationFrame(update);
      } else {
        element.textContent = target.toLocaleString();
      }
    }

    requestAnimationFrame(update);
  }

  // Simulan lang pag nakita na sa viewport, para hindi sayang
  // sa mga card na nasa ilalim pa.
  function initCountUpAnimations() {

    const statValues = document.querySelectorAll('.stat__value[data-count-up="true"], .stat__value[data-target]');
    if (!statValues.length) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCountUp(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    statValues.forEach(el => observer.observe(el));
  }

  // Mirror ng FieldFormatter.format_year_level sa server.
  function formatYearLevel(value) {
    if (!value) return '';
    const cleaned = value.trim();
    if (!cleaned) return '';

    const patterns = [
      { re: /^year\s*([1-5])$/i, fmt: m => 'Year ' + m[1] },
      { re: /^([1-5])(?:st|nd|rd|th)\s*year$/i, fmt: m => 'Year ' + m[1] },
      { re: /^([1-5])$/, fmt: m => 'Year ' + m[1] },
      { re: /^intern$/i, fmt: () => 'Intern' },
    ];

    for (const p of patterns) {
      const m = cleaned.match(p.re);
      if (m) return p.fmt(m);
    }

    return cleaned.replace(/\s+/g, ' ');
  }

  // Mirror ng format_campus. Yung acronyms, uppercase pa rin.
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

    return cleaned.split(/(\s+)/).map(w => {
      if (!w || w.trim() === '') return w;
      const upper = w.toUpperCase();
      if (acronyms.has(upper)) return upper;
      if (/^[a-zA-Z]/.test(w)) return w[0].toUpperCase() + w.slice(1).toLowerCase();
      return w;
    }).join('');
  }

  // Pag umalis sa field, i-format agad yung year level at campus.
  function initFormatters() {

    document.querySelectorAll('input[name="year_level"]').forEach(input => {
      input.addEventListener('blur', () => {
        const formatted = formatYearLevel(input.value);
        if (formatted !== input.value) {
          input.value = formatted;
        }
      });
    });

    document.querySelectorAll('input[name="campus"]').forEach(input => {
      input.addEventListener('blur', () => {
        const formatted = formatCampus(input.value);
        if (formatted !== input.value) {
          input.value = formatted;
        }
      });
    });
  }

  // Naka-expose para puwedeng tawagin manually kung kailangan.
  window.NUDentalConnect = {
    enhanceAllForms,
    validateField,
    validateForm: handleFormSubmit,
    formatYearLevel,
    formatCampus,
    initCountUpAnimations,
    initFormatters,
  };

  // Simulan lahat pag ready na yung DOM. Tapos observe ng bagong
  // form sa DOM para ma-enhance din.
  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        enhanceAllForms();
        initCountUpAnimations();
        initFormatters();
        initPasswordToggles();
        initStudentFields();
      });
    } else {
      enhanceAllForms();
      initCountUpAnimations();
      initFormatters();
      initPasswordToggles();
    }

    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.matches('form')) {
              enhanceAllForms();
            } else {
              node.querySelectorAll('form').forEach(function () { enhanceAllForms(); });
            }
          }
        });
      });
    });

    observer.observe(document.body, { childList: true, subtree: true });
  }

  init();
})();
