import { Recipe } from '@/lib/restaurant/recipe'
import RecipeJson from '@/store/recipe.json'
import { Effect } from 'effect'

export const sandboxRecipe = Recipe.create(RecipeJson).pipe(Effect.runSync)
