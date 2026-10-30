import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { Layout } from "../Layout";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import heartbeatFixture from "../../../../public/data-state/heartbeat.json";

function renderLayout(initialEntries = ["/"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<div data-testid="outlet-content">Overview Content</div>} />
          <Route path="/scanner" element={<div>Scanner Content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe("Layout accessibility and structure (Phase P7-B)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useSnapshotStore.getState().setSnapshotsDirectly({
      heartbeat: heartbeatFixture as any,
    });
  });

  it("labels brand and renders all 7 VibeTrade navigation items", () => {
    renderLayout();

    expect(screen.getByLabelText("VibeTrade v1.1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Market Scanner" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Opportunity Queue" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AI Research Room" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Paper Portfolio" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Performance" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "System Monitor" })).toBeInTheDocument();

    expect(screen.getByTestId("outlet-content")).toBeInTheDocument();
  });

  it("displays Heartbeat status badge in header", () => {
    renderLayout();
    expect(screen.getByText("HEALTHY")).toBeInTheDocument();
  });

  it("supports sidebar collapse and expand toggle", () => {
    renderLayout();
    const collapseBtn = screen.getByLabelText("Collapse sidebar");
    fireEvent.click(collapseBtn);

    const expandBtn = screen.getByLabelText("Expand sidebar");
    expect(expandBtn).toBeInTheDocument();
    fireEvent.click(expandBtn);

    expect(screen.getByLabelText("Collapse sidebar")).toBeInTheDocument();
  });

  it("does not crash when localStorage access is blocked", () => {
    const originalGetItem = window.localStorage.getItem;
    window.localStorage.getItem = () => {
      throw new Error("SecurityError: access denied");
    };

    try {
      expect(() => renderLayout()).not.toThrow();
    } finally {
      window.localStorage.getItem = originalGetItem;
    }
  });

  it("handles refresh button click", () => {
    renderLayout();
    const refreshBtn = screen.getByTitle("Refresh static snapshots from data-state");
    expect(refreshBtn).toBeInTheDocument();
    fireEvent.click(refreshBtn);
  });
});
