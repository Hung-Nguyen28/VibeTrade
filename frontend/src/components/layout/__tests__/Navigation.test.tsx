import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { SidebarNavigation } from "../SidebarNavigation";
import { PageHelp } from "../PageHelp";

function renderNavigation(path = "/", collapsed = false) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SidebarNavigation collapsed={collapsed} />
      <PageHelp />
    </MemoryRouter>
  );
}

describe("VibeTrade v1.1 Sidebar Navigation (Phase P7-B)", () => {
  it("renders all 7 core quant intelligence screens directly", () => {
    renderNavigation("/");

    const links = screen.getAllByRole("link");
    const hrefs = links.map((l) => l.getAttribute("href"));

    expect(hrefs).toContain("/");
    expect(hrefs).toContain("/scanner");
    expect(hrefs).toContain("/queue");
    expect(hrefs).toContain("/research");
    expect(hrefs).toContain("/portfolio");
    expect(hrefs).toContain("/performance");
    expect(hrefs).toContain("/monitor");

    expect(screen.getByRole("link", { name: "Overview" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("marks active page correctly when navigating to /scanner", () => {
    renderNavigation("/scanner");
    expect(screen.getByRole("link", { name: "Market Scanner" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("marks active page correctly when navigating to /research", () => {
    renderNavigation("/research");
    expect(screen.getByRole("link", { name: "AI Research Room" })).toHaveAttribute(
      "aria-current",
      "page"
    );
  });

  it("retains links in compact sidebar mode", () => {
    renderNavigation("/portfolio", true);
    const link = screen.getByRole("link", { name: "Paper Portfolio" });
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("opens mobile navigation menu when toggle clicked and closes on Escape", () => {
    renderNavigation("/", true);
    const menuBtn = screen.getByLabelText("Toggle navigation menu");
    fireEvent.click(menuBtn);

    expect(screen.getByLabelText("Mobile Navigation Drawer")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByLabelText("Mobile Navigation Drawer")).not.toBeInTheDocument();
  });

  it("closes drawer when a navigation item is clicked", () => {
    renderNavigation("/", true);
    const menuBtn = screen.getByLabelText("Toggle navigation menu");
    fireEvent.click(menuBtn);

    const drawer = screen.getByLabelText("Mobile Navigation Drawer");
    const scannerLink = drawer.querySelector('a[href="/scanner"]');
    if (scannerLink) {
      fireEvent.click(scannerLink);
    }
    expect(screen.queryByLabelText("Mobile Navigation Drawer")).not.toBeInTheDocument();
  });
});
