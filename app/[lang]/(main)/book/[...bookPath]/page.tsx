import MenuItemList from '@/components/MenuItemList'
import StageSelector from '@/components/StageSelector'
import {
  getAvailableDeluxeEditions,
  getLegacyRecipeAlias,
  getLocalizedName,
  isRecipeLocale,
  resolveBookSelection,
} from '@/lib/restaurant/catalog'
import { loadBookRecipeJson } from '@/lib/restaurant/restaurant.server'
import { Metadata } from 'next'
import { setRequestLocale } from 'next-intl/server'
import { notFound, redirect } from 'next/navigation'

export default async function StagePage({
  params,
}: {
  params: Promise<{ bookPath: string[]; lang: string }>
}) {
  const { bookPath, lang } = await params
  setRequestLocale(lang)

  if (!isRecipeLocale(lang)) notFound()

  const { selection, stageId } = resolveBookPath(lang, bookPath)
  const recipeJson = await loadBookRecipeJson(lang, selection)
  const stage = recipeJson.stages.find((stage) => stage.id === stageId)
  if (!stage) notFound()

  const stages = recipeJson.stages.map((stage) => ({
    id: stage.id,
    name: getLocalizedName(stage.name, lang),
  }))

  return (
    <>
      <StageSelector
        stageId={stageId}
        sourceId={selection.sourceId}
        isDeluxe={selection.kind === 'deluxe'}
        stages={stages}
        editions={selection.kind === 'deluxe' ? getAvailableDeluxeEditions(lang) : []}
        customRestaurantInfo={selection.kind === 'custom' ? selection.info : null}
      />
      <MenuItemList stageId={stageId} recipeJson={recipeJson} />
    </>
  )
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ bookPath: string[]; lang: string }>
}): Promise<Metadata> {
  const { bookPath, lang } = await params

  if (!isRecipeLocale(lang)) notFound()

  const { selection, stageId } = resolveBookPath(lang, bookPath)
  const recipeJson = await loadBookRecipeJson(lang, selection)
  const stage = recipeJson.stages.find((stage) => stage.id === stageId)
  if (!stage) notFound()

  return {
    title: `${getLocalizedName(stage.name, lang)} - OW Restaurant`,
  } satisfies Metadata
}

function resolveBookPath(lang: Parameters<typeof resolveBookSelection>[0], bookPath: string[]) {
  if (bookPath.length === 1) {
    const stageId = parseStageId(bookPath[0])
    redirect(`/${lang}/book/org/${stageId}`)
  }

  if (bookPath.length !== 2) notFound()

  const [sourceId, stageIdText] = bookPath
  const stageId = parseStageId(stageIdText)
  const legacyEditionId = getLegacyRecipeAlias(lang, sourceId)
  if (legacyEditionId) redirect(`/${lang}/book/${legacyEditionId}/${stageId}`)

  const selection = resolveBookSelection(lang, sourceId)
  if (!selection) notFound()

  return { selection, stageId }
}

function parseStageId(value: string): number {
  if (!/^\d+$/.test(value)) notFound()
  return Number(value)
}
