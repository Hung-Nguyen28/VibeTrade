import { useEffect, useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { Link, useLocation } from "react-router";
import { cn } from "@/lib/utils";
import { isNavigationActive, NAVIGATION_ITEMS } from "./navigation";

export function SidebarNavigation({ collapsed }: { collapsed: boolean }) {
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname, collapsed]);

  useEffect(() => {
    if (!menuOpen) return;
    panelRef.current?.querySelector<HTMLElement>("a")?.focus();
    const close = () => setMenuOpen(false);
    const dismiss = (event: MouseEvent) => {
      if (
        !panelRef.current?.contains(event.target as Node) &&
        !triggerRef.current?.contains(event.target as Node)
      ) {
        close();
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", close);
    };
  }, [menuOpen]);

  const renderNavList = (compact: boolean, isDrawer = false) => (
    <div className="space-y-1">
      {NAVIGATION_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = isNavigationActive(item.to, pathname);
        return (
          <Link
            key={item.id}
            to={item.to}
            aria-label={item.label}
            aria-current={active ? "page" : undefined}
            title={`${item.label} — ${item.description}`}
            onClick={() => setMenuOpen(false)}
            className={cn(
              "flex items-center rounded-lg text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
              compact ? "justify-center p-2.5" : "gap-3 px-3 py-2.5",
              !compact && !isDrawer && "max-md:justify-center max-md:p-2.5",
              active
                ? "bg-primary/15 text-primary font-semibold shadow-sm"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
            {!compact && (
              <span className={cn(!isDrawer && "max-md:hidden")}>{item.label}</span>
            )}
          </Link>
        );
      })}
    </div>
  );

  return (
    <>
      <nav
        aria-label="VibeTrade Navigation"
        className={cn(
          "flex-1 overflow-y-auto",
          collapsed ? "p-1.5" : "p-3 max-md:p-1.5"
        )}
      >
        <button
          ref={triggerRef}
          type="button"
          aria-label="Toggle navigation menu"
          title="Toggle menu"
          aria-expanded={menuOpen}
          aria-controls="sidebar-feature-menu"
          onClick={() => setMenuOpen((open) => !open)}
          className={cn(
            "flex w-full justify-center rounded-lg border border-border/60 p-2.5 text-muted-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 mb-2",
            !collapsed && "md:hidden"
          )}
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </button>
        {renderNavList(collapsed)}
      </nav>

      {menuOpen && (
        <nav
          ref={panelRef}
          id="sidebar-feature-menu"
          aria-label="Mobile Navigation Drawer"
          className="fixed inset-y-0 start-12 z-40 w-[min(18rem,calc(100vw-3rem))] space-y-3 overflow-y-auto border-e bg-card p-4 shadow-xl"
        >
          <div className="flex items-center justify-between pb-2 border-b border-border/60 text-sm font-semibold">
            <span>Navigation</span>
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => {
                setMenuOpen(false);
                triggerRef.current?.focus();
              }}
              className="rounded-md p-1.5 hover:bg-muted text-muted-foreground"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {renderNavList(false, true)}
        </nav>
      )}
    </>
  );
}
