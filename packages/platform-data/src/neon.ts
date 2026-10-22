import { neon } from "@neondatabase/serverless";

import type { DatabaseClient, QueryResult } from "./database.ts";

export function createNeonDatabase(connectionString: string): DatabaseClient {
  if (!/^postgres(?:ql)?:\/\//.test(connectionString)) {
    throw new TypeError("A postgres:// or postgresql:// connection string is required.");
  }

  const sql = neon(connectionString, { fullResults: true });
  return {
    async query<Row extends Record<string, unknown>>(
      text: string,
      params: readonly unknown[] = [],
    ): Promise<QueryResult<Row>> {
      const result = await sql.query(text, [...params]);
      return { rows: result.rows as Row[] };
    },
  };
}
