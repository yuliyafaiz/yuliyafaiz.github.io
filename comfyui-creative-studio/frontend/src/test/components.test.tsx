import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ParamField } from "../components/params";
import { Progress, StatusBadge } from "../components/ui";
import { detectFormat } from "../pages/Workflows";
import { workflow } from "./fixtures";

describe("detectFormat", () => {
  it("distinguishes API and UI workflow JSON", () => {
    expect(detectFormat({ "3": { class_type: "KSampler", inputs: {} } })).toBe("api");
    expect(detectFormat({ prompt: { "3": { class_type: "KSampler", inputs: {} } } })).toBe("api");
    expect(detectFormat({ nodes: [], links: [] })).toBe("ui");
    expect(detectFormat({ foo: 1 })).toBeNull();
    expect(detectFormat([1, 2])).toBeNull();
  });
});

describe("StatusBadge / Progress", () => {
  it("labels every job state distinctly", () => {
    const { rerender } = render(<StatusBadge status="submitted" />);
    expect(screen.getByTestId("status")).toHaveTextContent("Queued");
    rerender(<StatusBadge status="lost" />);
    expect(screen.getByTestId("status")).toHaveTextContent("Lost");
    rerender(<StatusBadge status="interrupted" />);
    expect(screen.getByTestId("status")).toHaveTextContent("Interrupted");
  });
  it("computes progress percentage", () => {
    render(<Progress value={5} max={20} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
  });
});

describe("ParamField", () => {
  it("renders text, number and choice controls and reports changes", async () => {
    const onChange = vi.fn();
    const [text, steps, sampler] = workflow.parameters;
    const { rerender } = render(<ParamField p={text} value={undefined} onChange={onChange} />);
    expect(screen.getByLabelText("Positive prompt")).toHaveValue("a ring");
    await userEvent.type(screen.getByLabelText("Positive prompt"), "!");
    expect(onChange).toHaveBeenLastCalledWith("a ring!");
    rerender(<ParamField p={steps} value={30} onChange={onChange} />);
    expect(screen.getByLabelText("Steps")).toHaveValue(30);
    rerender(<ParamField p={sampler} value={undefined} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Sampler"), "dpmpp_2m");
    expect(onChange).toHaveBeenLastCalledWith("dpmpp_2m");
  });
  it("flags a value missing on the server", () => {
    render(<ParamField p={{ ...workflow.parameters[2], default: "old_sampler" }} value={undefined} onChange={() => {}} />);
    expect(screen.getByText("old_sampler (not on server)")).toBeInTheDocument();
  });
});
