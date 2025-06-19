import json
import logging

from typing import Any, Dict, List, NamedTuple, IO, Optional, Tuple, Union

from kloppy.domain import (
    Provider,
    EventDataset,
    EventFactory,
    Metadata,
    Team,
    Player,
    DatasetFlag,
    Period,
    Event,
    Point,
)
from kloppy.infra.serializers.event.deserializer import EventDataDeserializer
from kloppy.exceptions import DeserializationError
from kloppy.utils import performance_logging

from . import specification as PFF

logger = logging.getLogger(__name__)


class PFFEventDataInput(NamedTuple):
    """
    Input data for PFF event deserialization.
    """

    event_data: IO[bytes]
    meta_data: IO[bytes]
    roster_data: IO[bytes]


class PFFEventDeserializer(EventDataDeserializer[PFFEventDataInput]):
    """
    Deserialize PFF events.
    """

    def __init__(self, coordinate_system: Optional[Union[str, Provider]] = None):
        super().__init__(
            coordinate_system=coordinate_system,
        )

    @property
    def provider(self) -> Provider:
        return Provider.PFF

    def load_raw_events(self, raw_event_data: IO[bytes]) -> dict[str, PFF.EVENT]:
        raw_events = {}
        events = json.load(raw_event_data)
        events = sorted(events, key=lambda x: x["eventTime"])
        for event in events:
            event_id = (
                f"{event['gameEventId']}_{event['possessionEventId']}_{event['gameEvents']['gameEventType']}_{event['eventTime']}"
                if event["possessionEventId"] is not None
                else f"{event['gameEventId']}"
            )
            raw_events[event_id] = PFF.event_decoder(event)
        return raw_events

    def load_data(
        self, inputs: PFFEventDataInput
    ) -> tuple[IO[bytes], IO[bytes], IO[bytes]]:
        """
        Load data from the input files.
        """
        return (
            self.load_raw_events(inputs.event_data),
            json.load(inputs.meta_data),
            json.load(inputs.roster_data),
        )

    def get_match_information(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get metadata from the input files.
        """
        return {
            "home_team": metadata["homeTeam"],
            "away_team": metadata["awayTeam"],
            "stadium": metadata["stadium"],
            "game_week": metadata["week"],
            "game_id": metadata["id"],
            "game_date": metadata["date"],
        }

    def get_pitch_information(
        self, stadium_metadata: Dict[str, Any]
    ) -> Tuple[float, float]:
        """
        Get pitch information from the metadata.
        """

        pitches: Dict[str, Any] = stadium_metadata["pitches"].pop()
        pitch_size_length = pitches["length"]
        pitch_size_width = pitches["width"]

        return pitch_size_width, pitch_size_length

    def build_player(self, player: Dict[str, Any], team: Team) -> Player:
        player = Player(
            player_id=player["player"]["id"],
            team=team,
            name=player["player"]["nickname"],
            jersey_no=int(player["shirtNumber"]),
            starting=player["started"],
            starting_position=player["positionGroupType"],
        )

        return player

    def build_squad(self, rooster_data: Dict[str, Any], team: Team) -> List[Player]:
        team_id = team.team_id

        players: List[Player] = [
            self.build_player(player_data, team_id)
            for player_data in rooster_data
            if player_data["team"]["id"] == team_id
        ]
        return players

    def build_team(
        self, team_data: Dict[str, Any], rooster_data: Dict[str, Any], ground_type: str
    ) -> Team:
        team_id = team_data["id"]

        team = Team(
            team_id=team_id,
            name=team_data["name"],
            ground=ground_type,
        )

        team.players = self.build_squad(rooster_data, team)

        return team

    def get_orientation(self, metadata: Dict[str, Any]) -> str:
        """
        Get the orientation of the event data.
        """

        is_home_team_left = metadata["homeTeamStartLeft"]

        orientation = "home-away" if is_home_team_left else "away-home"

        return orientation

    def get_metadata_information(
        self,
        match_information: Dict[str, Any],
        teams: List[Team],
        orientation: str,
        periods: str,
    ) -> Metadata:
        additional_metadata = {}

        metadata = Metadata(
            game_id=match_information["game_id"],
            game_week=match_information["game_week"],
            date=match_information["game_date"],
            teams=teams,
            pitch_dimensions=self.transformer.get_to_coordinate_system().pitch_dimensions,
            frame_rate=None,
            orientation=orientation,
            flags=DatasetFlag.BALL_OWNING_TEAM | DatasetFlag.BALL_STATE,
            score=None,
            provider=self.provider,
            coordinate_system=self.transformer.get_to_coordinate_system(),
            periods=periods,
            **additional_metadata,
        )

        return metadata

    def get_period_data(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get the period data from the metadata.
        """

        period_data = {
            "first_period": {
                "id": 1,
                "start_timestamp": metadata["startPeriod1"],
                "end_timestamp": metadata["endPeriod1"],
            },
            "second_period": {
                "id": 2,
                "start_timestamp": metadata["startPeriod2"],
                "end_timestamp": metadata["endPeriod2"],
            },
        }

        return period_data

    def build_periods(self, metadata: Dict[str, Any]) -> List[Period]:
        """
        Get the periods of the event data.
        """

        period_data = self.get_period_data(metadata)

        periods = [Period(**data) for _, data in period_data.items()]

        return periods

    def _extract_coordinates(
        self, event: Dict[str, Any], player_id: str, team_id: str, home_team_id: str
    ) -> Point:
        """
        Extract the coordinates from the event data.
        """

        player_list_index = "homePlayers" if team_id == home_team_id else "awayPlayers"

        player_list = event[player_list_index]

        coordinates_list = [
            {
                "x": player["x"],
                "y": player["y"],
            }
            for player in player_list
            if player["playerId"] == player_id
        ]

        if coordinates_list:
            coordinates = coordinates_list.pop()
            return Point(x=coordinates["x"], y=coordinates["y"])
        return Point(x=None, y=None)

    def _extract_possession_team(
        self,
        team_id: str,
        home_team: Team,
        away_team: Team,
    ) -> Team:
        return home_team if home_team.team_id == team_id else away_team

    def _extract_ball_state(self, event: Dict[str, Any]) -> str:
        return "dead" if event["gameEvents"]["gameEventType"] == "OUT" else "alive"

    def _extract_player(self, player_id: str, team: Team) -> Player:
        player_list = [
            player for player in team.players if player.player_id == player_id
        ]
        return player_list.pop() if player_list else None

    def build_generic_event_kwargs(
        self,
        event: Dict[str, Any],
        home_team: Team,
        away_team: Team,
    ) -> Dict[str, Any]:
        team_id = str(event["gameEvents"]["teamId"])
        team = home_team if team_id == home_team.team_id else away_team
        player_id = event["gameEvents"]["playerId"]
        coordinates = self._extract_coordinates(
            event=event,
            player_id=player_id,
            team_id=team_id,
            home_team_id=home_team.team_id,
        )

        return {
            "period": event["gameEvents"]["period"],
            "timestamp": event["possessionEvents"]["gameClock"],
            "ball_owning_team": self._extract_possession_team(
                team_id=event,
                home_team=home_team,
                away_team=away_team,
            ),
            "ball_state": self._extract_ball_state(event=event),
            "event_id": event["gameEventId"],
            "team": team,
            "player": self._extract_player(str(player_id), team),
            "coordinates": coordinates,
            "raw_event": event,
        }

    def transform_event(
        self,
        event: Dict[str, Any],
        home_team: Team,
        away_team: Team,
    ) -> Event:
        """
        Transform the event data to the desired format.
        """

        generic_event_kwargs = self.build_generic_event_kwargs(
            event=event,
            home_team=home_team,
            away_team=away_team,
        )

        return generic_event_kwargs

    def build_events(
        self,
        raw_events: List[Dict[str, Any]],
        home_team: Team,
        away_team: Team,
    ) -> List[Dict[str, Any]]:
        """
        Build the events from the raw event data.
        """

        events = [
            self.transform_event(
                event=event,
                home_team=home_team,
                away_team=away_team,
            )
            for event in raw_events
        ]

        return events

    def deserialize(self, inputs: PFFEventDataInput) -> EventDataset:
        """
        Deserialize the PFF event.
        """
        try:
            with performance_logging("load data", logger=logger):
                raw_events, meta_data, roster_data = self.load_data(inputs)

            with performance_logging("parse data", logger=logger):
                actual_meta_data = meta_data.pop()

                metadata_information = self.get_match_information(actual_meta_data)

                pitch_size_width, pitch_size_length = self.get_pitch_information(
                    metadata_information["stadium"]
                )

                self.transformer = self.get_transformer(
                    pitch_length=pitch_size_length,
                    pitch_width=pitch_size_width,
                    provider=self.provider,
                )

            with performance_logging("parse teams", logger=logger):
                home_team = self.build_team(
                    team_data=metadata_information["home_team"],
                    rooster_data=roster_data,
                    ground_type="home",
                )

                away_team = self.build_team(
                    team_data=metadata_information["away_team"],
                    rooster_data=roster_data,
                    ground_type="away",
                )

                teams = [home_team, away_team]

            with performance_logging("parse periods", logger=logger):
                periods = self.build_periods(
                    metadata=actual_meta_data,
                )

            with performance_logging("parse metadata", logger=logger):
                orientation = self.get_orientation(actual_meta_data)

                metadata = self.get_metadata_information(
                    match_information=metadata_information,
                    teams=teams,
                    orientation=orientation,
                    periods=periods,
                )

            with performance_logging("parse events", logger=logger):
                # events = self.build_events(
                #     raw_events=raw_events,
                #     home_team=home_team,
                #     away_team=away_team,
                # )
                events = []

                for raw_event in raw_events.values():
                    new_events = raw_event.set_refs(
                        periods, teams, raw_events
                    ).deserialize(self.event_factory)
                    for event in new_events:
                        if self.should_include_event(event):
                            event = self.transformer.transform_event(event)
                            events.append(event)

            return EventDataset(records=events, metadata=metadata)

        except Exception as e:
            raise DeserializationError(
                "Failed to create transformer for PFF event data"
            ) from e
