export function learnerDeviceToken(request: Request): string | undefined {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("CadenceDevice ")) return undefined;
  const token = authorization.slice("CadenceDevice ".length);
  return /^[A-Za-z0-9_-]{43}$/.test(token) ? token : undefined;
}
