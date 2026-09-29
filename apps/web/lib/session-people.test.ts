import { describe, expect, it } from 'vitest';

import type { PrincipalResponse } from '@/lib/backend-api';
import {
  addsSomeoneToRow,
  messageAuthorResolver,
  sessionRowPeople,
  transcriptBylines,
} from '@/lib/session-people';

function person(id: string, name: string): PrincipalResponse {
  return { type: 'user', id, name, avatar_image_uri: null, emoji: null, updated_at: null };
}

const owner = person('owner', 'Olive');
const ada = person('ada', 'Ada');
const bo = person('bo', 'Bo');

function user(id: string, sender: string | null, senderName: string | null = null) {
  return {
    type: 'message' as const,
    message: { id, sender_type: 'USER', sender_user_id: sender, sender_user_display_name: senderName },
  };
}

function agent(id: string) {
  return {
    type: 'message' as const,
    message: { id, sender_type: 'AGENT', sender_user_id: null, sender_user_display_name: null },
  };
}

describe('sessionRowPeople', () => {
  it('draws nothing for a session one person writes in', () => {
    expect(sessionRowPeople({ participants: [] })).toEqual([]);
    expect(sessionRowPeople({ participants: [owner] })).toEqual([]);
  });

  it('shows everyone once more than one person has written', () => {
    expect(sessionRowPeople({ participants: [owner, ada] })).toEqual([owner, ada]);
    expect(sessionRowPeople({ participants: [owner, ada, bo] })).toEqual([owner, ada, bo]);
  });
});

describe('messageAuthorResolver', () => {
  it('is null for a solo session', () => {
    expect(messageAuthorResolver([owner])).toBeNull();
    expect(messageAuthorResolver(undefined)).toBeNull();
  });

  it('reads a sender-less message as the owner and a known sender as themselves', () => {
    const authorOf = messageAuthorResolver([owner, ada])!;
    expect(authorOf(user('1', null).message)).toBe(owner);
    expect(authorOf(user('2', 'ada').message)).toBe(ada);
  });

  it('names a sender the list does not know yet from the message', () => {
    const authorOf = messageAuthorResolver([owner, ada])!;
    expect(authorOf(user('3', 'bo', 'Bo').message)).toMatchObject({ id: 'bo', name: 'Bo' });
  });

  it("names an in-flight message as the viewer's, only once the viewer is known", () => {
    expect(messageAuthorResolver([owner, ada], 'ada')!(user('optimistic-1', null).message)).toBe(ada);
    expect(messageAuthorResolver([owner, ada])!(user('optimistic-1', null).message)).toBeNull();
  });
});

describe('transcriptBylines', () => {
  it('is empty for a solo session', () => {
    expect(transcriptBylines([user('1', 'owner')], messageAuthorResolver([owner])).size).toBe(0);
  });

  it('names the first message of each run by one person', () => {
    const bylines = transcriptBylines(
      [
        { type: 'separator' },
        user('1', 'owner'),
        user('2', 'owner'),
        agent('3'),
        user('4', 'owner'),
        user('5', 'ada'),
        user('6', 'ada'),
        { type: 'tool-group' },
        user('7', 'ada'),
      ],
      messageAuthorResolver([owner, ada]),
    );
    expect([...bylines].map(([id, who]) => [id, who.id])).toEqual([
      ['1', 'owner'],
      ['4', 'owner'],
      ['5', 'ada'],
      ['7', 'ada'],
    ]);
  });

  it('treats a terminal-typed message as the owner continuing a run', () => {
    const bylines = transcriptBylines(
      [user('1', 'owner'), user('2', null)],
      messageAuthorResolver([owner, ada]),
    );
    expect([...bylines.keys()]).toEqual(['1']);
  });
});

describe('addsSomeoneToRow', () => {
  it('ignores the owner, terminal input and people already in the session', () => {
    expect(addsSomeoneToRow({ participants: [] }, 'owner', 'owner')).toBe(false);
    expect(addsSomeoneToRow({ owner, participants: [] }, 'owner', 'ada')).toBe(false);
    expect(addsSomeoneToRow({ participants: [owner, ada] }, 'ada', 'owner')).toBe(false);
    expect(addsSomeoneToRow({ participants: [] }, null, 'owner')).toBe(false);
  });

  it('flags a first message from anyone else', () => {
    expect(addsSomeoneToRow({ participants: [] }, 'ada', 'owner')).toBe(true);
    expect(addsSomeoneToRow({ owner, participants: [] }, 'bo', 'ada')).toBe(true);
  });

  it("flags the viewer's own first message in someone else's session", () => {
    // It turns that session into one with two people in it.
    expect(addsSomeoneToRow({ owner, participants: [] }, 'ada', 'ada')).toBe(true);
    expect(addsSomeoneToRow({ owner, participants: [] }, 'ada', null)).toBe(true);
  });

  it('waits for the viewer on their own rows', () => {
    expect(addsSomeoneToRow({ participants: [] }, 'ada', null)).toBe(false);
  });
});
