from datetime import timedelta
from typing import Dict, List, Optional, Union

from kloppy.domain import (
    ActionValue,
    Event,
    Frame,
    Period,
    Player,
    PlayerData,
    Point,
    Point3D,
    PositionType,
    Team,
)
from kloppy.domain.models.event import QualifierT
from kloppy.domain.services.frame_factory import create_frame
from kloppy.exceptions import DeserializationError


def get_team_by_id(team_id: Optional[int], teams: list[Team]) -> Optional[Team]:
    """Get a team by its id."""
    if team_id is None:
        return None
    if str(team_id) == teams[0].team_id:
        return teams[0]
    elif str(team_id) == teams[1].team_id:
        return teams[1]
    else:
        raise DeserializationError(f"Unknown team_id {team_id}")


def get_period_by_id(period_id: int, periods: list[Period]) -> Period:
    """Get a period by its id."""
    for period in periods:
        if period.id == period_id:
            return period
    raise DeserializationError(f"Unknown period_id {period_id}")


def find_player(player_id: Union[int, str], teams: list[Team]) -> Optional[Player]:
    for team in teams:
        player = team.get_player_by_id(player_id)
        if player is not None:
            return player


def parse_coordinates(
    player: Player | None, raw_event: dict[str, object]
) -> Point | None:
    """Parse PFF coordinates into a kloppy Point."""
    if player is None:
        return None

    players = raw_event["homePlayers"] + raw_event["awayPlayers"]

    try:
        player_dict = next(
            player_dict
            for player_dict in players
            if str(player_dict["playerId"]) == player.player_id
        )

        return Point(
            x=player_dict["x"],
            y=player_dict["y"],
        )
    except StopIteration:
        raise DeserializationError(f"Unknown player {player}")


def collect_qualifiers(*qualifiers: QualifierT | None) -> list[QualifierT]:
    return [q for q in qualifiers if q is not None]
