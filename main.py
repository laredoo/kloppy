from kloppy import pff
# from socceraction.spadl.kloppy import convert_to_actions

from mplsoccer import Pitch

# event.coordinates.x
# event.coordinates.y


def main():
    dataset = pff.load_event(
        event_data="/home/jupiter/ufmg/thesis/gandula-expected-goals/data/01_raw/event_data/3812.json",
        meta_data="/home/jupiter/ufmg/thesis/gandula-expected-goals/data/01_raw/metadata/3812.json",
        roster_data="/home/jupiter/ufmg/thesis/gandula-expected-goals/data/01_raw/rosters/3812.json",
        coordinates="pff",
    )


if __name__ == "__main__":
    main()
