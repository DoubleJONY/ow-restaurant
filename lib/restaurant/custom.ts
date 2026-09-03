export interface CustomRestaurantInfo {
  name: string
  code: string
  recipeId: string
}

export const CustomRestaurantInfos: CustomRestaurantInfo[] = [
  {
    name: '3호점',
    code: 'ST6Z6',
    recipeId: 'third',
  },
  {
    name: '뉴 3호점',
    code: 'SSZ1Z1',
    recipeId: 'new-third',
  },
  {
    name: 'Cafe (中文)',
    code: 'WM3MW',
    recipeId: 'cafe-zh-CN',
  },
]

export function getCustomRestaurantInfo(recipeId: string | null): CustomRestaurantInfo | null {
  if (recipeId === null) return null
  return CustomRestaurantInfos.find((info) => info.recipeId === recipeId) || null
}

export const FormUrl = 'https://forms.gle/7q6RrbwRUAfo6UWbA'
