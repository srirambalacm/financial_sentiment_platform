import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api/client";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; message: string; unreachable: boolean }
  | { status: "success"; data: T };

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: React.DependencyList
): [AsyncState<T>, () => void] {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setState({
            status: "error",
            message: err.message,
            unreachable: err.unreachable,
          });
        } else {
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "Unknown error",
            unreachable: false,
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);

  return [state, retry];
}
