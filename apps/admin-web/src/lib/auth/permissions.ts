export function can(
  permissions: readonly string[],
  permission: string,
  isSuperuser = false,
) {
  return isSuperuser || permissions.includes(permission);
}

export function canAny(
  permissions: readonly string[],
  required: readonly string[],
  isSuperuser = false,
) {
  return (
    isSuperuser ||
    required.some((permission) => permissions.includes(permission))
  );
}

export function canAll(
  permissions: readonly string[],
  required: readonly string[],
  isSuperuser = false,
) {
  return (
    isSuperuser ||
    required.every((permission) => permissions.includes(permission))
  );
}
