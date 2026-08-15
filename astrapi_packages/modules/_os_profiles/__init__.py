"""astrapi_packages.modules._os_profiles – Container fuer OS-Profile.

Der Unterstrich im Ordnernamen sorgt dafuer, dass module_registry.py's
Verzeichnis-Scan (_load_from_dir, ueberspringt Eintraege mit "_"-Praefix)
die enthaltenen Profile (debian/, archlinux/) NICHT automatisch als
eigenstaendige Module registriert. Stattdessen importiert astrapi_packages._app
gezielt nur die Profile, die ueber die Einstellung "Aktive Betriebssysteme"
(Modul packages_config) freigeschaltet sind.
"""
