import { describe, it, expect } from "vitest";
import { HistoryStack, DEFAULT_STUDIO_TRANSFORM } from "../HistoryStack";

describe("HistoryStack (ADR-10 Diff-based Undo/Redo)", () => {
  it("initializes with default transform and empty history", () => {
    const stack = new HistoryStack();
    expect(stack.canUndo()).toBe(false);
    expect(stack.canRedo()).toBe(false);
    expect(stack.getCurrentState()).toEqual(DEFAULT_STUDIO_TRANSFORM);
  });

  it("pushes new state, enables undo, and clears redo", () => {
    const stack = new HistoryStack();
    const modified = {
      ...DEFAULT_STUDIO_TRANSFORM,
      rotation: 90,
      filters: { ...DEFAULT_STUDIO_TRANSFORM.filters, brightness: 25 },
    };

    stack.push(modified);
    expect(stack.canUndo()).toBe(true);
    expect(stack.canRedo()).toBe(false);
    expect(stack.getCurrentState().rotation).toBe(90);
    expect(stack.getCurrentState().filters.brightness).toBe(25);
  });

  it("undoes to previous state and redoes back", () => {
    const stack = new HistoryStack();
    const state1 = {
      ...DEFAULT_STUDIO_TRANSFORM,
      rotation: 45,
    };
    const state2 = {
      ...DEFAULT_STUDIO_TRANSFORM,
      rotation: 90,
    };

    stack.push(state1);
    stack.push(state2);

    expect(stack.getCurrentState().rotation).toBe(90);

    // Undo -> state1
    const undone1 = stack.undo();
    expect(undone1?.rotation).toBe(45);
    expect(stack.canRedo()).toBe(true);

    // Undo -> initial
    const undone2 = stack.undo();
    expect(undone2?.rotation).toBe(0);
    expect(stack.canUndo()).toBe(false);

    // Redo -> state1
    const redone1 = stack.redo();
    expect(redone1?.rotation).toBe(45);

    // Redo -> state2
    const redone2 = stack.redo();
    expect(redone2?.rotation).toBe(90);
    expect(stack.canRedo()).toBe(false);
  });

  it("ignores push if state is identical to current present", () => {
    const stack = new HistoryStack();
    stack.push(DEFAULT_STUDIO_TRANSFORM);
    expect(stack.canUndo()).toBe(false);
  });

  it("respects maxDepth limit", () => {
    const stack = new HistoryStack(DEFAULT_STUDIO_TRANSFORM, 3);
    for (let i = 1; i <= 5; i++) {
      stack.push({
        ...DEFAULT_STUDIO_TRANSFORM,
        rotation: i * 10,
      });
    }

    // Should only be able to undo 3 times
    expect(stack.undo()?.rotation).toBe(40);
    expect(stack.undo()?.rotation).toBe(30);
    expect(stack.undo()?.rotation).toBe(20);
    expect(stack.canUndo()).toBe(false);
  });
});

