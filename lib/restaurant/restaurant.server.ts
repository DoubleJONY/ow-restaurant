import 'server-only'

import {
  BookSelection,
  CustomRecipeId,
  DeluxeEditionId,
  RecipeLocale,
} from '@/lib/restaurant/catalog'
import type { RecipeJson } from '@/lib/restaurant/recipe'
import { cache } from 'react'

type RecipeJsonModule = { default: RecipeJson }
type RecipeJsonLoader = () => Promise<RecipeJsonModule>

const deluxeRecipeLoaders: Record<
  Exclude<RecipeLocale, 'zh-CN'>,
  Record<DeluxeEditionId, RecipeJsonLoader>
> = {
  ko: {
    org: () => import('@/store/recipe-deluxe-ko-org.json'),
    cafe: () => import('@/store/recipe-deluxe-ko-cafe.json'),
    gc: () => import('@/store/recipe-deluxe-ko-gc.json'),
  },
  en: {
    org: () => import('@/store/recipe-deluxe-en-org.json'),
    cafe: () => import('@/store/recipe-deluxe-en-cafe.json'),
    gc: () => import('@/store/recipe-deluxe-en-gc.json'),
  },
  ja: {
    org: () => import('@/store/recipe-deluxe-ja-org.json'),
    cafe: () => import('@/store/recipe-deluxe-ja-cafe.json'),
    gc: () => import('@/store/recipe-deluxe-ja-gc.json'),
  },
}

const customRecipeLoaders = {
  third: () => import('@/store/recipe-third.json'),
  'new-third': () => import('@/store/recipe-new-third.json'),
  'cafe-zh-CN': () => import('@/store/recipe-cafe-zh-CN.json'),
} satisfies Record<CustomRecipeId, RecipeJsonLoader>

const loadDeluxeRecipeJson = cache(
  async (locale: RecipeLocale, editionId: DeluxeEditionId): Promise<RecipeJson> => {
    if (locale === 'zh-CN') {
      if (editionId !== 'org') throw new Error(`Unsupported Deluxe edition: ${locale}/${editionId}`)
      return (await import('@/store/recipe.json')).default as RecipeJson
    }

    return (await deluxeRecipeLoaders[locale][editionId]()).default
  }
)

const loadCustomRecipeJson = cache(async (sourceId: keyof typeof customRecipeLoaders) => {
  return (await customRecipeLoaders[sourceId]()).default as RecipeJson
})

export async function loadBookRecipeJson(
  locale: RecipeLocale,
  selection: BookSelection
): Promise<RecipeJson> {
  if (selection.kind === 'deluxe') {
    return loadDeluxeRecipeJson(locale, selection.sourceId)
  }

  return loadCustomRecipeJson(selection.sourceId)
}
