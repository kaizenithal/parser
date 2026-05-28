******************************************************************
      * CUSTOMER ACCOUNT MANAGEMENT SYSTEM
      * Processes daily transactions and updates account balances.
      * Reads transaction file, validates against master, writes report.
      ******************************************************************

       IDENTIFICATION DIVISION.
       PROGRAM-ID.    CUSTMGMT.
       AUTHOR.        J SMITH.
       DATE-WRITTEN.  2024-01-15.
       DATE-COMPILED.

       ENVIRONMENT DIVISION.

       CONFIGURATION SECTION.
       SOURCE-COMPUTER. IBM-390.
       OBJECT-COMPUTER. IBM-390.

       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRANSACTION-FILE
               ASSIGN TO 'TRANFILE'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-TRAN-STATUS.

           SELECT MASTER-FILE
               ASSIGN TO 'MASTFILE'
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS MF-ACCOUNT-NUM
               FILE STATUS IS WS-MAST-STATUS.

           SELECT REPORT-FILE
               ASSIGN TO 'RPTFILE'
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-RPT-STATUS.

       DATA DIVISION.

       FILE SECTION.

       FD  TRANSACTION-FILE
           RECORDING MODE IS F
           BLOCK CONTAINS 0 RECORDS.
       01  TRANSACTION-RECORD.
           05  TR-ACCOUNT-NUM        PIC X(10).
           05  TR-TRANS-TYPE         PIC X(01).
               88  TR-DEPOSIT        VALUE 'D'.
               88  TR-WITHDRAWAL     VALUE 'W'.
               88  TR-TRANSFER       VALUE 'T'.
           05  TR-AMOUNT             PIC 9(07)V99.
           05  TR-DATE               PIC 9(08).
           05  TR-DESCRIPTION        PIC X(30).
           05  FILLER                PIC X(24).

       FD  MASTER-FILE.
       01  MASTER-RECORD.
           05  MF-ACCOUNT-NUM        PIC X(10).
           05  MF-CUSTOMER-NAME      PIC X(30).
           05  MF-ACCOUNT-TYPE       PIC X(01).
               88  MF-CHECKING       VALUE 'C'.
               88  MF-SAVINGS        VALUE 'S'.
           05  MF-BALANCE            PIC S9(09)V99.
           05  MF-LAST-ACTIVITY      PIC 9(08).
           05  MF-STATUS             PIC X(01).
               88  MF-ACTIVE         VALUE 'A'.
               88  MF-CLOSED         VALUE 'C'.
               88  MF-FROZEN         VALUE 'F'.

       FD  REPORT-FILE.
       01  REPORT-LINE               PIC X(132).

       WORKING-STORAGE SECTION.

       01  WS-FILE-STATUSES.
           05  WS-TRAN-STATUS        PIC XX.
           05  WS-MAST-STATUS        PIC XX.
           05  WS-RPT-STATUS         PIC XX.

       01  WS-FLAGS.
           05  WS-EOF-FLAG           PIC X(01) VALUE 'N'.
               88  END-OF-FILE       VALUE 'Y'.
               88  NOT-END-OF-FILE   VALUE 'N'.

       01  WS-COUNTERS.
           05  WS-TRANS-READ         PIC 9(07) VALUE ZEROS.
           05  WS-TRANS-PROCESSED    PIC 9(07) VALUE ZEROS.
           05  WS-TRANS-REJECTED     PIC 9(07) VALUE ZEROS.
           05  WS-TOTAL-DEPOSITS     PIC S9(11)V99 VALUE ZEROS.
           05  WS-TOTAL-WITHDRAWALS  PIC S9(11)V99 VALUE ZEROS.

       01  WS-WORK-FIELDS.
           05  WS-NEW-BALANCE        PIC S9(09)V99.
           05  WS-FORMATTED-AMT      PIC $$$,$$$,$$9.99.
           05  WS-FORMATTED-BAL      PIC -$$$,$$$,$$9.99.
           05  WS-CURRENT-DATE.
               10  WS-CURR-YEAR     PIC 9(04).
               10  WS-CURR-MONTH    PIC 9(02).
               10  WS-CURR-DAY      PIC 9(02).

      * Copybook for standard error handling routines
       COPY ERRHANDL.

      * Copybook for report formatting
       COPY RPTFMT.

       01  WS-REPORT-HEADER.
           05  FILLER                PIC X(30)
               VALUE 'DAILY TRANSACTION REPORT      '.
           05  WS-HDR-DATE           PIC X(10).
           05  FILLER                PIC X(92) VALUE SPACES.

       01  WS-DETAIL-LINE.
           05  WS-DET-ACCOUNT        PIC X(10).
           05  FILLER                PIC X(02) VALUE SPACES.
           05  WS-DET-NAME           PIC X(30).
           05  FILLER                PIC X(02) VALUE SPACES.
           05  WS-DET-TYPE           PIC X(10).
           05  FILLER                PIC X(02) VALUE SPACES.
           05  WS-DET-AMOUNT         PIC $$$,$$$,$$9.99.
           05  FILLER                PIC X(02) VALUE SPACES.
           05  WS-DET-NEW-BAL        PIC -$$$,$$$,$$9.99.
           05  FILLER                PIC X(02) VALUE SPACES.
           05  WS-DET-STATUS         PIC X(10).

       PROCEDURE DIVISION.

      ******************************************************************
      * MAIN CONTROL PARAGRAPH
      ******************************************************************
       0000-MAIN-CONTROL.
           PERFORM 1000-INITIALIZE
           PERFORM 2000-PROCESS-TRANSACTIONS
               UNTIL END-OF-FILE
           PERFORM 3000-FINALIZE
           STOP RUN.

      ******************************************************************
      * INITIALIZATION - OPEN FILES AND WRITE HEADERS
      ******************************************************************
       1000-INITIALIZE.
           OPEN INPUT  TRANSACTION-FILE
           OPEN I-O    MASTER-FILE
           OPEN OUTPUT REPORT-FILE

           IF WS-TRAN-STATUS NOT = '00'
               DISPLAY 'ERROR OPENING TRANSACTION FILE: '
                   WS-TRAN-STATUS
               PERFORM 9000-ABORT-PROGRAM
           END-IF

           IF WS-MAST-STATUS NOT = '00'
               DISPLAY 'ERROR OPENING MASTER FILE: '
                   WS-MAST-STATUS
               PERFORM 9000-ABORT-PROGRAM
           END-IF

           MOVE FUNCTION CURRENT-DATE TO WS-CURRENT-DATE
           STRING WS-CURR-YEAR '-' WS-CURR-MONTH '-' WS-CURR-DAY
               DELIMITED BY SIZE
               INTO WS-HDR-DATE
           END-STRING

           WRITE REPORT-LINE FROM WS-REPORT-HEADER

           PERFORM 8000-READ-TRANSACTION.

      ******************************************************************
      * MAIN PROCESSING LOOP
      ******************************************************************
       2000-PROCESS-TRANSACTIONS.
           ADD 1 TO WS-TRANS-READ

           MOVE TR-ACCOUNT-NUM TO MF-ACCOUNT-NUM
           READ MASTER-FILE
               INVALID KEY
                   PERFORM 2100-HANDLE-NOT-FOUND
               NOT INVALID KEY
                   PERFORM 2200-VALIDATE-AND-UPDATE
           END-READ

           PERFORM 8000-READ-TRANSACTION.

       2100-HANDLE-NOT-FOUND.
           ADD 1 TO WS-TRANS-REJECTED
           MOVE TR-ACCOUNT-NUM TO WS-DET-ACCOUNT
           MOVE 'NOT FOUND' TO WS-DET-NAME
           MOVE SPACES TO WS-DET-TYPE
           MOVE TR-AMOUNT TO WS-DET-AMOUNT
           MOVE ZEROS TO WS-DET-NEW-BAL
           MOVE 'REJECTED' TO WS-DET-STATUS
           WRITE REPORT-LINE FROM WS-DETAIL-LINE.

       2200-VALIDATE-AND-UPDATE.
           IF MF-FROZEN
               ADD 1 TO WS-TRANS-REJECTED
               MOVE 'FROZEN' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           ELSE IF MF-CLOSED
               ADD 1 TO WS-TRANS-REJECTED
               MOVE 'CLOSED' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           ELSE
               EVALUATE TRUE
                   WHEN TR-DEPOSIT
                       PERFORM 2300-PROCESS-DEPOSIT
                   WHEN TR-WITHDRAWAL
                       PERFORM 2400-PROCESS-WITHDRAWAL
                   WHEN TR-TRANSFER
                       PERFORM 2500-PROCESS-TRANSFER
                   WHEN OTHER
                       ADD 1 TO WS-TRANS-REJECTED
                       MOVE 'BAD TYPE' TO WS-DET-STATUS
                       PERFORM 2900-WRITE-DETAIL
               END-EVALUATE
           END-IF.

       2300-PROCESS-DEPOSIT.
           ADD TR-AMOUNT TO MF-BALANCE
               GIVING WS-NEW-BALANCE
           MOVE WS-NEW-BALANCE TO MF-BALANCE
           MOVE TR-DATE TO MF-LAST-ACTIVITY
           REWRITE MASTER-RECORD

           ADD TR-AMOUNT TO WS-TOTAL-DEPOSITS
           ADD 1 TO WS-TRANS-PROCESSED
           MOVE 'DEPOSIT' TO WS-DET-TYPE
           MOVE 'PROCESSED' TO WS-DET-STATUS
           PERFORM 2900-WRITE-DETAIL.

       2400-PROCESS-WITHDRAWAL.
           SUBTRACT TR-AMOUNT FROM MF-BALANCE
               GIVING WS-NEW-BALANCE

           IF WS-NEW-BALANCE < ZEROS
               ADD 1 TO WS-TRANS-REJECTED
               MOVE 'NSF' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           ELSE
               MOVE WS-NEW-BALANCE TO MF-BALANCE
               MOVE TR-DATE TO MF-LAST-ACTIVITY
               REWRITE MASTER-RECORD

               ADD TR-AMOUNT TO WS-TOTAL-WITHDRAWALS
               ADD 1 TO WS-TRANS-PROCESSED
               MOVE 'WITHDRAWAL' TO WS-DET-TYPE
               MOVE 'PROCESSED' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           END-IF.

       2500-PROCESS-TRANSFER.
           SUBTRACT TR-AMOUNT FROM MF-BALANCE
               GIVING WS-NEW-BALANCE

           IF WS-NEW-BALANCE < ZEROS
               ADD 1 TO WS-TRANS-REJECTED
               MOVE 'NSF' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           ELSE
               MOVE WS-NEW-BALANCE TO MF-BALANCE
               MOVE TR-DATE TO MF-LAST-ACTIVITY
               REWRITE MASTER-RECORD
               ADD 1 TO WS-TRANS-PROCESSED
               MOVE 'TRANSFER' TO WS-DET-TYPE
               MOVE 'PROCESSED' TO WS-DET-STATUS
               PERFORM 2900-WRITE-DETAIL
           END-IF.

       2900-WRITE-DETAIL.
           MOVE TR-ACCOUNT-NUM TO WS-DET-ACCOUNT
           MOVE MF-CUSTOMER-NAME TO WS-DET-NAME
           MOVE TR-AMOUNT TO WS-DET-AMOUNT
           MOVE MF-BALANCE TO WS-DET-NEW-BAL
           WRITE REPORT-LINE FROM WS-DETAIL-LINE.

      ******************************************************************
      * FINALIZATION - WRITE SUMMARY AND CLOSE FILES
      ******************************************************************
       3000-FINALIZE.
           MOVE WS-TOTAL-DEPOSITS TO WS-FORMATTED-AMT
           DISPLAY 'TOTAL DEPOSITS:     ' WS-FORMATTED-AMT
           MOVE WS-TOTAL-WITHDRAWALS TO WS-FORMATTED-AMT
           DISPLAY 'TOTAL WITHDRAWALS:  ' WS-FORMATTED-AMT
           DISPLAY 'TRANSACTIONS READ:      ' WS-TRANS-READ
           DISPLAY 'TRANSACTIONS PROCESSED: ' WS-TRANS-PROCESSED
           DISPLAY 'TRANSACTIONS REJECTED:  ' WS-TRANS-REJECTED

           CLOSE TRANSACTION-FILE
                 MASTER-FILE
                 REPORT-FILE.

      ******************************************************************
      * UTILITY PARAGRAPHS
      ******************************************************************
       8000-READ-TRANSACTION.
           READ TRANSACTION-FILE
               AT END
                   SET END-OF-FILE TO TRUE
               NOT AT END
                   CONTINUE
           END-READ.

       9000-ABORT-PROGRAM.
           DISPLAY '*** PROGRAM ABORTED ***'
           CLOSE TRANSACTION-FILE
                 MASTER-FILE
                 REPORT-FILE
           STOP RUN.