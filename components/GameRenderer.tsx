import useGameManager from '@/lib/game/game-manager'
import { Item } from '@/lib/restaurant/item'
import { sandboxRecipe } from '@/lib/restaurant/sandbox-recipe'
import { extend, useApplication } from '@pixi/react'
import { Effect } from 'effect'
import { Container } from 'pixi.js'

extend({
  Container,
})

export default function GameRenderer({
  stageId,
  onItemCreate,
}: {
  stageId: number
  onItemCreate: (item: Item) => void
}) {
  const { app } = useApplication()

  const stage = sandboxRecipe.getStage(stageId).pipe(Effect.runSync)
  const fridge = stage.fridge

  const gameManager = useGameManager(app, fridge, onItemCreate)

  return <pixiContainer sortableChildren={true} />
}
