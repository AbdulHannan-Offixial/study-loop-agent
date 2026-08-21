document.addEventListener("DOMContentLoaded", () => {
    console.log("StudyLoop interface loaded.");

    const appShell = document.getElementById("appShell");
    const sidebarToggle = document.getElementById("sidebarToggle");

    // Restore saved toggle state
    const isCollapsed = localStorage.getItem("sidebarCollapsed") === "true";
    if (isCollapsed && appShell) {
        appShell.classList.add("sidebar-collapsed");
    }

    // Add toggle listener
    if (sidebarToggle && appShell) {
        sidebarToggle.addEventListener("click", () => {
            appShell.classList.toggle("sidebar-collapsed");
            const collapsed = appShell.classList.contains("sidebar-collapsed");
            localStorage.setItem("sidebarCollapsed", collapsed);
        });
    }
});