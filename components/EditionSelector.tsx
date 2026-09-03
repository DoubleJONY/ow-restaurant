import { Link } from '@/i18n/routing'

export interface EditionSelectorEdition {
  id: string
  name: string
}

export default function EditionSelector({
  editions,
  activeEditionId,
  buildHref,
  label,
}: {
  editions: readonly EditionSelectorEdition[]
  activeEditionId: string
  buildHref: (id: string) => string
  label?: string
}) {
  if (editions.length < 2) return null

  return (
    <div className="flex flex-col gap-6">
      {label && <div className="text-gray text-12 font-bold">{label}</div>}
      <nav
        role="tablist"
        aria-label={label ?? 'Restaurant edition'}
        className="bg-primary-background rounded-8 no-scrollbar tablet:w-fit flex w-full gap-2 overflow-x-auto p-2"
      >
        {editions.map((edition) => {
          const active = edition.id === activeEditionId

          return (
            <Link
              key={edition.id}
              href={buildHref(edition.id)}
              role="tab"
              aria-selected={active}
              aria-current={active ? 'page' : undefined}
              data-active={active}
              className="text-primary data-[active=true]:bg-primary rounded-8 text-12 tablet:grow-0 flex min-w-fit grow items-center justify-center px-12 py-6 font-semibold whitespace-nowrap transition-colors data-[active=true]:text-white"
            >
              {edition.name}
            </Link>
          )
        })}
      </nav>
    </div>
  )
}
