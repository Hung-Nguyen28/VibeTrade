import { render, screen, fireEvent } from "@testing-library/react";
import { ConnectionBanner } from "../ConnectionBanner";
import { useSnapshotStore } from "@/stores/useSnapshotStore";
import heartbeatFixture from "../../../../public/data-state/heartbeat.json";

describe("ConnectionBanner Heartbeat Health & Staleness (Phase P7-B)", () => {
  beforeEach(() => {
    useSnapshotStore.setState({
      error: null,
      isStale: false,
      refreshing: false,
      heartbeat: heartbeatFixture as any,
    });
  });

  it("renders nothing when heartbeat is healthy and fresh", () => {
    const { container } = render(<ConnectionBanner />);
    expect(container.innerHTML).toBe("");
  });

  it("renders amber warning banner when heartbeat is stale or degraded", () => {
    useSnapshotStore.setState({
      isStale: true,
      heartbeat: {
        ...heartbeatFixture,
        status: "DEGRADED",
        schedule_drift_ms: 1250,
      } as any,
    });

    render(<ConnectionBanner />);

    expect(screen.getByText(/Pipeline Degraded \/ Stale:/)).toBeInTheDocument();
    expect(screen.getByText("DEGRADED")).toBeInTheDocument();
    expect(screen.getByText("1250ms")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Refresh Snapshots/i })
    ).toBeInTheDocument();
  });

  it("renders error alert banner when snapshots fail to load", () => {
    useSnapshotStore.setState({
      error: "Network error 404: heartbeat.json not found",
    });

    render(<ConnectionBanner />);

    expect(screen.getByText(/Snapshot Load Error:/)).toBeInTheDocument();
    expect(
      screen.getByText(/Network error 404: heartbeat.json not found/)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });

  it("handles retry click on error", () => {
    const loadSpy = vi.fn();
    useSnapshotStore.setState({
      error: "Some network failure",
      loadSnapshots: loadSpy,
    });

    render(<ConnectionBanner />);
    const retryBtn = screen.getByRole("button", { name: /Retry/i });
    fireEvent.click(retryBtn);

    expect(loadSpy).toHaveBeenCalledWith(true);
  });
});
