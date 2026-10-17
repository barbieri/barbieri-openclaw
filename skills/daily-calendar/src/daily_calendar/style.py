"""Generated Gustavo Style include. See design/README.md."""

CSS = """
/* Generated from barbieri-playground/design/DESIGN.md. Do not edit tokens. */
:root{color-scheme:light dark;
--surface:#ffffff;
--surface-sunken:#f6f7f9;
--surface-raised:#ffffff;
--border:#e5e7eb;
--border-strong:#d8dee8;
--text:#1f2937;
--text-muted:#64748b;
--accent:#2563eb;
--accent-strong:#1d4ed8;
--accent-soft:#eef2ff;
--success:#047857;
--success-bg:#ecfdf5;
--error:#b91c1c;
--error-bg:#fef2f2;
--warning:#b45309;
--warning-bg:#fffbeb;
--info:#1d4ed8;
--info-bg:#eff6ff;
--positive:#16a34a;
--negative:#dc2626;
}

@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--surface:#1f2937;
--surface-sunken:#111827;
--surface-raised:#243044;
--border:#374151;
--border-strong:#4b5563;
--text:#f9fafb;
--text-muted:#9ca3af;
--accent:#60a5fa;
--accent-strong:#93c5fd;
--accent-soft:#1e3a8a;
--success:#34d399;
--success-bg:#064e3b;
--error:#fb7185;
--error-bg:#4c0519;
--warning:#fbbf24;
--warning-bg:#451a03;
--info:#60a5fa;
--info-bg:#1e3a8a;
--positive:#4ade80;
--negative:#f87171;
}
}

:root[data-theme=light]{color-scheme:light;
--surface:#ffffff;
--surface-sunken:#f6f7f9;
--surface-raised:#ffffff;
--border:#e5e7eb;
--border-strong:#d8dee8;
--text:#1f2937;
--text-muted:#64748b;
--accent:#2563eb;
--accent-strong:#1d4ed8;
--accent-soft:#eef2ff;
--success:#047857;
--success-bg:#ecfdf5;
--error:#b91c1c;
--error-bg:#fef2f2;
--warning:#b45309;
--warning-bg:#fffbeb;
--info:#1d4ed8;
--info-bg:#eff6ff;
--positive:#16a34a;
--negative:#dc2626;
}

:root[data-theme=dark]{color-scheme:dark;
--surface:#1f2937;
--surface-sunken:#111827;
--surface-raised:#243044;
--border:#374151;
--border-strong:#4b5563;
--text:#f9fafb;
--text-muted:#9ca3af;
--accent:#60a5fa;
--accent-strong:#93c5fd;
--accent-soft:#1e3a8a;
--success:#34d399;
--success-bg:#064e3b;
--error:#fb7185;
--error-bg:#4c0519;
--warning:#fbbf24;
--warning-bg:#451a03;
--info:#60a5fa;
--info-bg:#1e3a8a;
--positive:#4ade80;
--negative:#f87171;
}

body{margin:0;
padding:24px;
background:#f6f7f9;
background:var(--surface-sunken);
color:#1f2937;
color:var(--text);
font:400 15px/1.5 Roboto, "Open Sans", "Helvetica Neue", Arial, sans-serif;
}

main{max-width:760px;
margin:auto;
padding:24px;
background:#ffffff;
background:var(--surface);
color:#1f2937;
color:var(--text);
border:1px solid var(--border);
border-radius:12px}

h1{font-size:24px;
font-weight:500}
h2{font-size:18px;
font-weight:500}
h3{font-size:16px;
font-weight:500}

a{color:#2563eb;
color:var(--accent);
text-decoration:underline}

table{width:100%;
border-collapse:collapse;
font-size:14px;
font-variant-numeric:tabular-nums}

th,td{border:1px solid var(--border-strong);
padding:8px;
text-align:left}
th{background:var(--accent-soft);
font-weight:500}

td.report-table-value{text-align:right}

hr{border:0;
border-top:1px solid var(--border);
margin:22px 0}

pre{white-space:pre-wrap;
overflow-wrap:anywhere;
background:#f6f7f9;
background:var(--surface-sunken);
color:#1f2937;
color:var(--text);
padding:16px;
border-radius:12px}

.material-icon{width:24px;
height:24px;
vertical-align:middle;
fill:currentColor;
margin-right:8px}

"""
