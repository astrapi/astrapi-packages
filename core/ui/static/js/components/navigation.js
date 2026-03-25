// Mobile sidebar management

function toggleSidebar() {
  var sidebar = document.getElementById('sidebar');
  var overlay = document.getElementById('sidebar-overlay');
  var isOpen  = sidebar.classList.contains('mobile-open');
  if (isOpen) {
    closeSidebar();
  } else {
    sidebar.classList.add('mobile-open');
    overlay.classList.add('visible');
    document.body.style.overflow = 'hidden';
  }
}

function closeSidebar() {
  var sidebar = document.getElementById('sidebar');
  var overlay = document.getElementById('sidebar-overlay');
  sidebar.classList.remove('mobile-open');
  overlay.classList.remove('visible');
  document.body.style.overflow = '';
}

// Nav-Klick auf Mobile → Sidebar schließen
document.addEventListener('htmx:afterSwap', function(e) {
  if (e.target && e.target.id === 'main-content' && window.innerWidth < 769) {
    closeSidebar();
  }
});

// Escape → Sidebar schließen
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeSidebar();
});
