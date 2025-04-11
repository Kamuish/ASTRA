"""Compute overlaps between multiple lists."""

from typing import List


def check_if_overlap(block_A, block_B) -> bool:
    """Check if there is an overlap between two blocks."""
    return block_B[0] <= block_A[0] <= block_B[1] or block_A[0] <= block_B[0] <= block_A[1]


def find_overlaps(input_blocks: List[List[float]]) -> List[List[float]]:
    """Loop over a list with 1D regions and find intersections among them.

    Used to decrease the number of "standalone" blocks in the telluric template

    E.g:

    This:

    |----| |----|
        |----|
    Will be merged into a single "block", as they are all intersected

    Parameters
    ----------
    input_blocks : List[List[float]]
        [description]

    Returns
    -------
    List[List[float]]
        [description]

    TODO
    ------

    - [ ] See if there is a need of porting this function to cython

    """
    found_overlap = False
    new_blocks = []
    found_matches = set()
    for block_index, block in enumerate(input_blocks):
        min_loc, max_loc = block

        if block_index in found_matches:
            # if the block has already been merged into another, ignore it!
            continue
        for comp_index, block_under_comp in enumerate(input_blocks[block_index + 1 :]):
            current_index = block_index + comp_index + 1

            if check_if_overlap(block, block_under_comp):
                found_overlap = True
                found_matches.add(current_index)

                min_loc = min(min_loc, block_under_comp[0])
                max_loc = max(max_loc, block_under_comp[1])

        if block_index not in found_matches:
            found_matches.add(block_index)
            new_blocks.append((min_loc, max_loc))

    if found_overlap:
        return find_overlaps(new_blocks)

    return input_blocks
