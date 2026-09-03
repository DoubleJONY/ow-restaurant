import type { CustomRestaurantInfo } from '@/lib/restaurant/custom'
import { getCustomRestaurantInfo } from '@/lib/restaurant/custom'

export const RecipeLocales = ['ko', 'en', 'ja', 'zh-CN'] as const

export type RecipeLocale = (typeof RecipeLocales)[number]
export type DeluxeEditionId = 'org' | 'cafe' | 'gc'
export type CustomRecipeId = 'third' | 'new-third' | 'cafe-zh-CN'
export type BookSourceId = DeluxeEditionId | CustomRecipeId

export interface DeluxeEditionInfo {
  id: DeluxeEditionId
  name: string
}

export type BookSelection =
  | {
      kind: 'deluxe'
      sourceId: DeluxeEditionId
    }
  | {
      kind: 'custom'
      sourceId: CustomRecipeId
      info: CustomRestaurantInfo
    }

const DeluxeEditionNames: Record<
  Exclude<RecipeLocale, 'zh-CN'>,
  Record<DeluxeEditionId, string>
> = {
  ko: {
    org: '모듬회밥!',
    cafe: '카페!',
    gc: '쿡제요리',
  },
  en: {
    org: 'OverwatchCooked!',
    cafe: 'Cafe & Dessert',
    gc: 'World Cuisine',
  },
  ja: {
    org: 'クラシック',
    cafe: 'カフェ&デザート',
    gc: '世界の料理',
  },
}

const CustomRecipeIds = new Set<CustomRecipeId>(['third', 'new-third', 'cafe-zh-CN'])
const DeluxeEditionIds = new Set<DeluxeEditionId>(['org', 'cafe', 'gc'])

export const LegacyRecipeAliases: Readonly<Record<string, DeluxeEditionId>> = {
  'cafe-en': 'cafe',
  'cook-intl': 'gc',
  'cook-intl-en': 'gc',
}

export function isRecipeLocale(locale: string): locale is RecipeLocale {
  return RecipeLocales.includes(locale as RecipeLocale)
}

export function isDeluxeEditionId(value: string): value is DeluxeEditionId {
  return DeluxeEditionIds.has(value as DeluxeEditionId)
}

export function isCustomRecipeId(value: string): value is CustomRecipeId {
  return CustomRecipeIds.has(value as CustomRecipeId)
}

export function supportsDeluxeEdition(locale: RecipeLocale, editionId: DeluxeEditionId): boolean {
  return editionId === 'org' || locale !== 'zh-CN'
}

export function getAvailableDeluxeEditions(locale: RecipeLocale): DeluxeEditionInfo[] {
  if (locale === 'zh-CN') return []

  return (['org', 'cafe', 'gc'] as const).map((id) => ({
    id,
    name: DeluxeEditionNames[locale][id],
  }))
}

export function getLegacyRecipeAlias(
  locale: RecipeLocale,
  sourceId: string
): DeluxeEditionId | null {
  if (locale === 'zh-CN') return null
  return LegacyRecipeAliases[sourceId] ?? null
}

export function resolveBookSelection(locale: RecipeLocale, sourceId: string): BookSelection | null {
  if (isDeluxeEditionId(sourceId) && supportsDeluxeEdition(locale, sourceId)) {
    return { kind: 'deluxe', sourceId }
  }

  if (!isCustomRecipeId(sourceId)) return null

  const info = getCustomRestaurantInfo(sourceId)
  if (!info) return null

  return { kind: 'custom', sourceId, info }
}

export function getLocalizedName(names: string[], locale: RecipeLocale): string {
  const localeIndex = RecipeLocales.indexOf(locale)
  return names[localeIndex] || names[0] || ''
}
