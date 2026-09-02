import { Effect, Exit } from "effect";
import { useEffect, useState } from "react";

export interface QueryState<A, E> {
  readonly loading: boolean;
  readonly data: A | null;
  readonly error: E | null;
}

/**
 * Runs an Effect as a fiber tied to the component's lifecycle: re-runs
 * whenever `deps` change, and interrupts the in-flight fiber on unmount /
 * dep change so a slow, stale request can never clobber a newer one.
 */
export function useEffectQuery<A, E>(
  effect: Effect.Effect<A, E>,
  deps: ReadonlyArray<unknown>,
): QueryState<A, E> {
  const [state, setState] = useState<QueryState<A, E>>({
    loading: true,
    data: null,
    error: null,
  });

  useEffect(() => {
    setState({ loading: true, data: null, error: null });

    const fiber = Effect.runFork(effect);
    fiber.addObserver((exit) => {
      if (Exit.isSuccess(exit)) {
        setState({ loading: false, data: exit.value, error: null });
      } else if (exit.cause._tag === "Fail") {
        setState({ loading: false, data: null, error: exit.cause.error });
      }
      // Interrupted (cleanup fired before completion): leave state as-is,
      // the next effect run will set it.
    });

    return () => {
      Effect.runFork(fiber.interruptAsFork(fiber.id()));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
