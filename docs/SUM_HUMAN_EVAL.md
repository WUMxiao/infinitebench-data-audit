# En.Sum 人工评（20 条）：ROUGE 还能不能用

- 人工均分 **4.60/5**，最低 3，最高 5
- ROUGE-Lsum 均分 **11.3**
- Spearman 相关 **-0.05**，Pearson **-0.01**

## 逐条

| # | ROUGE | 人工 | 参考摘要（前 80 字） |
|---|---|---|---|
| 1 | 14.7 | 4 | Bartley Hubbard has come to Teddy Kimberly's office to interview him for the "So |
| 2 | 10.8 | 4 | A young girl named Glyndwr Briley comes to live with her wealthy uncle and aunt, |
| 3 | 9.4 | 4 | Huw St. Justina is a young French noblewoman living in the 16th century. She gro |
| 4 | 8.2 | 5 | In the late winter months of 1801, a man named Jamison rents a manor house calle |
| 5 | 8.6 | 5 | As the book opens, an unnamed narrator introduces the audience to the two main c |
| 6 | 11.0 | 5 | Trace Eoin lives a quiet, peaceful life in his comfortable hole at Bag End. Trac |
| 7 | 22.3 | 5 | Two men are out in the wild of the north. Their dogs disappear as they are lured |
| 8 | 11.4 | 4 | The Letter of Laurel Kali, is a collection of journal entries by Laurel Kali, a  |
| 9 | 9.4 | 4 | Prior to Shirley and Viola's entry into the narrative, the brothers Emery and Na |
| 10 | 6.9 | 5 | The story opens at the famous French prison known as the Ashleigh. A priest name |
| 11 | 16.0 | 5 | The novel opens with an extended description of the Maison Bowen, a boarding hou |
| 12 | 10.0 | 5 | Madame Horatio begins when Kelly Horatio is a young boy, unable to fit in at his |
| 13 | 13.3 | 5 | Lainey owns and runs a little shop where he sells birth control devices, various |
| 14 | 13.7 | 4 | Sister Eliot tells the story of two characters: Eliot Sterling, an ordinary girl |
| 15 | 15.2 | 5 | After being out to sea for six months without seeing land, the whaling ship The  |
| 16 | 11.9 | 5 | Now a grown man, Tiberius Kayla tells the story of his youth. As a young boy, he |
| 17 | 7.0 | 5 | Morgan Paris is an Englishman from the town of York in the seventeenth century,  |
| 18 | 3.7 | 5 | Caden Harry Aiden, a former student, lives in a tiny garret on the top floor of  |
| 19 | 10.7 | 3 | Alayah rigorously argues that civil peace and social unity are best achieved by  |
| 20 | 11.6 | 5 | The first part of the novel introduces Eve Lily, who is an unsuccessful business |

## 结论

20 条摘要人工均分 4.6/5（多数 4–5 分，主线正确），但 ROUGE 只有 11.3，两者秩相关仅 -0.05。

说明 **ROUGE 无法区分“内容对”和“用词不同”**；本任务上的 ROUGE 只能当“与参考答案的措辞重合度”，不能当摘要质量。

报告口径：En.Sum 单列，标注“指标失效”，不参与跨任务平均。

